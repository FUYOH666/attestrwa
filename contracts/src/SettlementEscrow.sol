// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.26;

import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {Ownable2Step} from "@openzeppelin/contracts/access/Ownable2Step.sol";

import {IEAS} from "@eas/IEAS.sol";
import {Attestation} from "@eas/Common.sol";

/// @title SettlementEscrow
/// @notice Reference consumer of AttestRWA decision records. Holds a buyer's
///         stablecoin deposit and settles it according to an on-chain
///         `SettlementDecision` attestation made by a trusted attester:
///         an APPROVE releases the funds to the payee the buyer named, a
///         REJECT lets the buyer take them back early. Without a decision
///         the buyer can refund after the deadline.
/// @dev    Funds can only ever move to the deal's payee or back to its buyer.
///         An attester (or the owner, by trusting a rogue attester) can decide
///         *which* of the two happens before the deadline, never redirect them.
///
///         Attestation data layout (schema `SettlementDecision`):
///
///         (bytes32 dealId, address payee, address token, uint256 amount,
///          uint8 decision, bytes32 policyHash, bytes32 recordHash)
///
///         `policyHash` and `recordHash` commit to the off-chain decision
///         record; this contract does not interpret them.
contract SettlementEscrow is ReentrancyGuard, Ownable2Step {
    using SafeERC20 for IERC20;

    enum DealStatus {
        None,
        Open,
        Released,
        Refunded
    }

    /// @notice State of one escrowed settlement.
    /// @param buyer        Depositor; the only address a refund can go to.
    /// @param deadline     Unix time at which release closes and refund opens.
    /// @param status       Lifecycle state.
    /// @param payee        Recipient named by the buyer; the only release target.
    /// @param depositedAt  Unix time of the deposit.
    /// @param token        ERC-20 token in custody.
    /// @param amount       Amount in token base units.
    struct Deal {
        address buyer;
        uint64 deadline;
        DealStatus status;
        address payee;
        uint64 depositedAt;
        address token;
        uint256 amount;
    }

    /// @notice `decision` value of an approving attestation.
    uint8 public constant DECISION_APPROVE = 1;

    /// @notice `decision` value of a rejecting attestation.
    uint8 public constant DECISION_REJECT = 2;

    /// @dev ABI-encoded length of the seven static schema fields.
    uint256 private constant DECISION_DATA_LENGTH = 224;

    /// @notice EAS contract this escrow reads attestations from.
    IEAS public immutable eas;

    /// @notice UID of the `SettlementDecision` schema. Immutable, so an
    ///         attestation under any other schema is never accepted.
    bytes32 public immutable schemaUid;

    /// @notice Attesters whose decisions this escrow acts on. Checked when an
    ///         attestation is used, so removing an attester invalidates every
    ///         decision it has outstanding.
    mapping(address attester => bool trusted) public trustedAttesters;

    /// @notice Tokens that may be deposited. Checked at deposit only.
    mapping(address token => bool allowed) public allowedTokens;

    mapping(bytes32 dealId => Deal deal) private _deals;

    // ---- Events --------------------------------------------------------

    event Deposited(
        bytes32 indexed dealId,
        address indexed buyer,
        address indexed payee,
        address token,
        uint256 amount,
        uint64 deadline,
        bytes32 salt
    );

    event SettlementReleased(
        bytes32 indexed dealId, address indexed payee, uint256 amount, bytes32 attestationUid
    );

    /// @param attestationUid The REJECT attestation used, or zero for a
    ///        refund after the deadline.
    event SettlementRefunded(
        bytes32 indexed dealId, address indexed buyer, uint256 amount, bytes32 attestationUid
    );

    event AttesterTrustChanged(address indexed attester, bool trusted);

    event TokenAllowanceChanged(address indexed token, bool allowed);

    // ---- Errors --------------------------------------------------------

    error InvalidEasAddress();
    error InvalidSchema();
    error InvalidPayee();
    error InvalidDeadline();
    error AmountZero();
    error TokenNotAllowed();
    error TransferAmountMismatch();
    error DealAlreadyExists();
    error DealNotOpen();
    error DeadlinePassed();
    error DeadlineNotReached();
    error CallerNotBuyer();
    error AttestationNotFound();
    error AttestationWrongSchema();
    error AttestationWrongRecipient();
    error AttesterNotTrusted();
    error AttestationRevoked();
    error AttestationExpired();
    error AttestationPredatesDeposit();
    error AttestationMalformed();
    error AttestationDealMismatch();
    error AttestationPayeeMismatch();
    error AttestationTokenMismatch();
    error AttestationAmountMismatch();
    error AttestationDecisionMismatch();

    // ---- Constructor ---------------------------------------------------

    /// @param easAddress         EAS contract on this chain.
    /// @param decisionSchemaUid  UID of the `SettlementDecision` schema.
    /// @param initialOwner       Admin of the attester and token lists. Should
    ///                           be a different key from any attester.
    /// @param tokens             Tokens allowed for deposit from the start.
    /// @param attesters          Attesters trusted from the start.
    constructor(
        address easAddress,
        bytes32 decisionSchemaUid,
        address initialOwner,
        address[] memory tokens,
        address[] memory attesters
    ) Ownable(initialOwner) {
        if (easAddress == address(0)) revert InvalidEasAddress();
        if (decisionSchemaUid == bytes32(0)) revert InvalidSchema();
        eas = IEAS(easAddress);
        schemaUid = decisionSchemaUid;
        for (uint256 i = 0; i < tokens.length; ++i) {
            _setToken(tokens[i], true);
        }
        for (uint256 i = 0; i < attesters.length; ++i) {
            _setAttester(attesters[i], true);
        }
    }

    // ---- Admin ---------------------------------------------------------

    /// @notice Trust or stop trusting an attester. Stopping trust is the
    ///         kill switch for a compromised attester key.
    function setAttester(address attester, bool trusted) external onlyOwner {
        _setAttester(attester, trusted);
    }

    /// @notice Allow or disallow a token for new deposits. Only plain ERC-20
    ///         tokens should be allowed: a fee-on-transfer token is rejected
    ///         at deposit, and a rebasing token would break deal accounting.
    function setToken(address token, bool allowed) external onlyOwner {
        _setToken(token, allowed);
    }

    // ---- Buyer flow ----------------------------------------------------

    /// @notice Identifier a deposit by `buyer` with `salt` gets. Bound to this
    ///         chain and this contract, so a decision cannot be replayed on
    ///         another deployment, and to the buyer, so nobody else can take it.
    function computeDealId(address buyer, bytes32 salt) public view returns (bytes32) {
        return keccak256(abi.encode(block.chainid, address(this), buyer, salt));
    }

    /// @notice Escrow `amount` of `token` for `payee`.
    /// @param  salt      Buyer-chosen value; one deposit per (buyer, salt).
    /// @param  payee     The only address a release can pay.
    /// @param  deadline  Unix time after which release is closed and the
    ///                   buyer can refund without a decision.
    /// @return dealId    Identifier of the new deal.
    function deposit(bytes32 salt, address payee, address token, uint256 amount, uint64 deadline)
        external
        nonReentrant
        returns (bytes32 dealId)
    {
        if (payee == address(0) || payee == address(this)) revert InvalidPayee();
        if (!allowedTokens[token]) revert TokenNotAllowed();
        if (amount == 0) revert AmountZero();
        if (deadline <= block.timestamp) revert InvalidDeadline();

        dealId = computeDealId(msg.sender, salt);
        if (_deals[dealId].status != DealStatus.None) revert DealAlreadyExists();

        _deals[dealId] = Deal({
            buyer: msg.sender,
            deadline: deadline,
            status: DealStatus.Open,
            payee: payee,
            depositedAt: uint64(block.timestamp),
            token: token,
            amount: amount
        });

        // The deal must be backed by exactly `amount`. Measuring the balance
        // around the transfer is safe here: every state-changing function of
        // this contract is nonReentrant, so a token callback cannot move this
        // contract's funds between the two reads.
        // slither-disable-start reentrancy-balance
        uint256 balanceBefore = IERC20(token).balanceOf(address(this));
        IERC20(token).safeTransferFrom(msg.sender, address(this), amount);
        if (IERC20(token).balanceOf(address(this)) - balanceBefore != amount) {
            revert TransferAmountMismatch();
        }
        // slither-disable-end reentrancy-balance

        emit Deposited(dealId, msg.sender, payee, token, amount, deadline, salt);
    }

    /// @notice Pay the payee, given an APPROVE decision for exactly this deal.
    /// @dev    Anyone may call; the protection is the attestation. Closed from
    ///         the deadline on, so release and refund never race.
    function release(bytes32 dealId, bytes32 attestationUid) external nonReentrant {
        Deal storage d = _deals[dealId];
        if (d.status != DealStatus.Open) revert DealNotOpen();
        if (block.timestamp >= d.deadline) revert DeadlinePassed();

        _checkDecision(attestationUid, dealId, d, DECISION_APPROVE);

        d.status = DealStatus.Released;
        IERC20(d.token).safeTransfer(d.payee, d.amount);

        emit SettlementReleased(dealId, d.payee, d.amount, attestationUid);
    }

    /// @notice Return the deposit to the buyer: after the deadline with no
    ///         attestation (`attestationUid == 0`), or at any time with a
    ///         REJECT decision for exactly this deal.
    function refund(bytes32 dealId, bytes32 attestationUid) external nonReentrant {
        Deal storage d = _deals[dealId];
        if (d.status != DealStatus.Open) revert DealNotOpen();
        if (msg.sender != d.buyer) revert CallerNotBuyer();

        if (attestationUid == bytes32(0)) {
            if (block.timestamp < d.deadline) revert DeadlineNotReached();
        } else {
            _checkDecision(attestationUid, dealId, d, DECISION_REJECT);
        }

        d.status = DealStatus.Refunded;
        IERC20(d.token).safeTransfer(d.buyer, d.amount);

        emit SettlementRefunded(dealId, d.buyer, d.amount, attestationUid);
    }

    // ---- Views ---------------------------------------------------------

    /// @notice Snapshot of a deal; `status` is `None` for an unknown id.
    function getDeal(bytes32 dealId) external view returns (Deal memory) {
        return _deals[dealId];
    }

    // ---- Internal ------------------------------------------------------

    function _setAttester(address attester, bool trusted) private {
        trustedAttesters[attester] = trusted;
        emit AttesterTrustChanged(attester, trusted);
    }

    function _setToken(address token, bool allowed) private {
        allowedTokens[token] = allowed;
        emit TokenAllowanceChanged(token, allowed);
    }

    /// @dev The single gate for both settlement paths. An attestation counts
    ///      only if it is a live decision by a trusted attester, addressed to
    ///      this contract, made after the deposit, about exactly this deal,
    ///      and says `expected`.
    function _checkDecision(bytes32 uid, bytes32 dealId, Deal storage d, uint8 expected)
        private
        view
    {
        Attestation memory a = eas.getAttestation(uid);
        if (a.uid == bytes32(0)) revert AttestationNotFound();
        if (a.schema != schemaUid) revert AttestationWrongSchema();
        if (a.recipient != address(this)) revert AttestationWrongRecipient();
        if (!trustedAttesters[a.attester]) revert AttesterNotTrusted();
        if (a.revocationTime != 0) revert AttestationRevoked();
        if (a.expirationTime != 0 && a.expirationTime <= block.timestamp) {
            revert AttestationExpired();
        }
        if (a.time < d.depositedAt) revert AttestationPredatesDeposit();
        if (a.data.length != DECISION_DATA_LENGTH) revert AttestationMalformed();

        (
            bytes32 attDealId,
            address attPayee,
            address attToken,
            uint256 attAmount,
            uint8 decision,,
        ) = abi.decode(a.data, (bytes32, address, address, uint256, uint8, bytes32, bytes32));

        if (attDealId != dealId) revert AttestationDealMismatch();
        if (attPayee != d.payee) revert AttestationPayeeMismatch();
        if (attToken != d.token) revert AttestationTokenMismatch();
        if (attAmount != d.amount) revert AttestationAmountMismatch();
        if (decision != expected) revert AttestationDecisionMismatch();
    }
}
