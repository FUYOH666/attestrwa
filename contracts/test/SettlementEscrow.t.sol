// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.26;

import {Ownable} from "@openzeppelin/contracts/access/Ownable.sol";
import {ISchemaResolver} from "@eas/resolver/ISchemaResolver.sol";

import {SettlementEscrow} from "../src/SettlementEscrow.sol";
import {EscrowFixture} from "./EscrowFixture.sol";
import {FeeOnTransferToken} from "./mocks/FeeOnTransferToken.sol";

contract SettlementEscrowTest is EscrowFixture {
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
    event SettlementRefunded(
        bytes32 indexed dealId, address indexed buyer, uint256 amount, bytes32 attestationUid
    );
    event AttesterTrustChanged(address indexed attester, bool trusted);
    event TokenAllowanceChanged(address indexed token, bool allowed);

    function setUp() public {
        _deployFixture();
    }

    // ---- schema and constructor ----------------------------------------

    function test_registered_schema_has_the_published_uid() public view {
        assertEq(schemaUid, PUBLISHED_SCHEMA_UID);
        assertEq(escrow.schemaUid(), PUBLISHED_SCHEMA_UID);
    }

    function test_constructor_reverts_on_zero_eas() public {
        address[] memory none = new address[](0);
        vm.expectRevert(SettlementEscrow.InvalidEasAddress.selector);
        new SettlementEscrow(address(0), schemaUid, owner, none, none);
    }

    function test_constructor_reverts_on_zero_schema() public {
        address[] memory none = new address[](0);
        vm.expectRevert(SettlementEscrow.InvalidSchema.selector);
        new SettlementEscrow(address(eas), bytes32(0), owner, none, none);
    }

    function test_constructor_records_configuration() public view {
        assertEq(address(escrow.eas()), address(eas));
        assertEq(escrow.owner(), owner);
        assertTrue(escrow.allowedTokens(address(usdc)));
        assertTrue(escrow.trustedAttesters(attester));
        assertFalse(escrow.trustedAttesters(owner));
        assertFalse(escrow.trustedAttesters(address(this)));
    }

    function test_deployer_gets_no_privileges() public {
        vm.expectRevert(
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, address(this))
        );
        escrow.setAttester(stranger, true);
    }

    // ---- admin ---------------------------------------------------------

    function test_setAttester_only_owner() public {
        vm.prank(stranger);
        vm.expectRevert(
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, stranger)
        );
        escrow.setAttester(stranger, true);
    }

    function test_setAttester_toggles_and_emits() public {
        vm.expectEmit(true, false, false, true);
        emit AttesterTrustChanged(stranger, true);
        vm.prank(owner);
        escrow.setAttester(stranger, true);
        assertTrue(escrow.trustedAttesters(stranger));

        vm.prank(owner);
        escrow.setAttester(stranger, false);
        assertFalse(escrow.trustedAttesters(stranger));
    }

    function test_setToken_only_owner() public {
        vm.prank(stranger);
        vm.expectRevert(
            abi.encodeWithSelector(Ownable.OwnableUnauthorizedAccount.selector, stranger)
        );
        escrow.setToken(address(usdc), false);
    }

    function test_setToken_toggles_and_emits() public {
        vm.expectEmit(true, false, false, true);
        emit TokenAllowanceChanged(address(usdc), false);
        vm.prank(owner);
        escrow.setToken(address(usdc), false);
        assertFalse(escrow.allowedTokens(address(usdc)));
    }

    function test_ownership_transfer_takes_two_steps() public {
        vm.prank(owner);
        escrow.transferOwnership(stranger);
        assertEq(escrow.owner(), owner, "owner changes only on acceptance");
        assertEq(escrow.pendingOwner(), stranger);

        vm.prank(stranger);
        escrow.acceptOwnership();
        assertEq(escrow.owner(), stranger);
    }

    // ---- deposit -------------------------------------------------------

    function test_deposit_stores_the_deal_and_pulls_funds() public {
        uint256 buyerBefore = usdc.balanceOf(buyer);
        bytes32 dealId = _deposit();

        SettlementEscrow.Deal memory d = escrow.getDeal(dealId);
        assertEq(d.buyer, buyer);
        assertEq(d.payee, payee);
        assertEq(d.token, address(usdc));
        assertEq(d.amount, AMOUNT);
        assertEq(d.deadline, deadline);
        assertEq(d.depositedAt, uint64(block.timestamp));
        assertEq(uint8(d.status), uint8(SettlementEscrow.DealStatus.Open));
        assertEq(usdc.balanceOf(address(escrow)), AMOUNT);
        assertEq(usdc.balanceOf(buyer), buyerBefore - AMOUNT);
    }

    function test_deposit_emits_event() public {
        bytes32 dealId = escrow.computeDealId(buyer, SALT);
        vm.expectEmit(true, true, true, true);
        emit Deposited(dealId, buyer, payee, address(usdc), AMOUNT, deadline, SALT);
        _deposit();
    }

    function test_deposit_derives_dealId_from_chain_escrow_buyer_salt() public {
        bytes32 dealId = _deposit();
        assertEq(dealId, keccak256(abi.encode(block.chainid, address(escrow), buyer, SALT)));
        assertEq(dealId, escrow.computeDealId(buyer, SALT));

        SettlementEscrow other = _newEscrow();
        assertTrue(other.computeDealId(buyer, SALT) != dealId, "bound to the escrow");

        vm.chainId(block.chainid + 1);
        assertTrue(escrow.computeDealId(buyer, SALT) != dealId, "bound to the chain");
    }

    function test_deposit_rejects_reused_salt() public {
        _deposit();
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.DealAlreadyExists.selector);
        escrow.deposit(SALT, payee, address(usdc), AMOUNT, deadline);
    }

    function test_salt_stays_spent_after_the_deal_settles() public {
        bytes32 dealId = _deposit();
        vm.warp(deadline);
        vm.prank(buyer);
        escrow.refund(dealId, bytes32(0));

        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.DealAlreadyExists.selector);
        escrow.deposit(SALT, payee, address(usdc), AMOUNT, deadline + 1 days);
    }

    function test_same_salt_different_buyers_do_not_collide() public {
        bytes32 first = _deposit();

        usdc.mint(stranger, AMOUNT);
        vm.startPrank(stranger);
        usdc.approve(address(escrow), AMOUNT);
        bytes32 second = escrow.deposit(SALT, payee, address(usdc), AMOUNT, deadline);
        vm.stopPrank();

        assertTrue(first != second);
        assertEq(escrow.getDeal(second).buyer, stranger);
        assertEq(usdc.balanceOf(address(escrow)), 2 * AMOUNT);
    }

    function test_deposit_rejects_zero_payee() public {
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.InvalidPayee.selector);
        escrow.deposit(SALT, address(0), address(usdc), AMOUNT, deadline);
    }

    function test_deposit_rejects_the_escrow_itself_as_payee() public {
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.InvalidPayee.selector);
        escrow.deposit(SALT, address(escrow), address(usdc), AMOUNT, deadline);
    }

    function test_deposit_rejects_unlisted_token() public {
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.TokenNotAllowed.selector);
        escrow.deposit(SALT, payee, address(0xBEEF), AMOUNT, deadline);
    }

    function test_deposit_rejects_delisted_token() public {
        vm.prank(owner);
        escrow.setToken(address(usdc), false);
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.TokenNotAllowed.selector);
        escrow.deposit(SALT, payee, address(usdc), AMOUNT, deadline);
    }

    function test_deposit_rejects_zero_amount() public {
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.AmountZero.selector);
        escrow.deposit(SALT, payee, address(usdc), 0, deadline);
    }

    function test_deposit_rejects_deadline_not_in_the_future() public {
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.InvalidDeadline.selector);
        escrow.deposit(SALT, payee, address(usdc), AMOUNT, uint64(block.timestamp));
    }

    function test_deposit_rejects_fee_on_transfer_token() public {
        FeeOnTransferToken fee = new FeeOnTransferToken();
        vm.prank(owner);
        escrow.setToken(address(fee), true);
        fee.mint(buyer, AMOUNT);

        vm.startPrank(buyer);
        fee.approve(address(escrow), AMOUNT);
        vm.expectRevert(SettlementEscrow.TransferAmountMismatch.selector);
        escrow.deposit(SALT, payee, address(fee), AMOUNT, deadline);
        vm.stopPrank();
    }

    // ---- release -------------------------------------------------------

    function test_release_pays_the_payee_on_an_approve_decision() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attest(dealId, APPROVE);

        vm.expectEmit(true, true, false, true);
        emit SettlementReleased(dealId, payee, AMOUNT, uid);
        escrow.release(dealId, uid);

        assertEq(usdc.balanceOf(payee), AMOUNT);
        assertEq(usdc.balanceOf(address(escrow)), 0);
        assertEq(uint8(escrow.getDeal(dealId).status), uint8(SettlementEscrow.DealStatus.Released));
    }

    function test_release_can_be_triggered_by_anyone_but_pays_only_the_payee() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attest(dealId, APPROVE);
        vm.prank(stranger);
        escrow.release(dealId, uid);
        assertEq(usdc.balanceOf(payee), AMOUNT);
        assertEq(usdc.balanceOf(stranger), 0);
    }

    function test_release_works_one_second_before_the_deadline() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attest(dealId, APPROVE);
        vm.warp(deadline - 1);
        escrow.release(dealId, uid);
        assertEq(usdc.balanceOf(payee), AMOUNT);
    }

    function test_release_is_closed_from_the_deadline_on() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attestRaw(
            attester,
            schemaUid,
            address(escrow),
            0,
            _data(dealId, payee, address(usdc), AMOUNT, APPROVE)
        );
        vm.warp(deadline);
        vm.expectRevert(SettlementEscrow.DeadlinePassed.selector);
        escrow.release(dealId, uid);
    }

    function test_release_unknown_deal_reverts() public {
        vm.expectRevert(SettlementEscrow.DealNotOpen.selector);
        escrow.release(keccak256("nope"), bytes32(uint256(1)));
    }

    function test_release_twice_reverts() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attest(dealId, APPROVE);
        escrow.release(dealId, uid);
        vm.expectRevert(SettlementEscrow.DealNotOpen.selector);
        escrow.release(dealId, uid);
    }

    function test_release_after_refund_reverts() public {
        bytes32 dealId = _deposit();
        bytes32 approve = _attest(dealId, APPROVE);
        _revoke(approve);
        bytes32 reject = _attest(dealId, REJECT);
        vm.prank(buyer);
        escrow.refund(dealId, reject);

        vm.expectRevert(SettlementEscrow.DealNotOpen.selector);
        escrow.release(dealId, approve);
    }

    function test_release_reverts_on_unknown_attestation() public {
        bytes32 dealId = _deposit();
        vm.expectRevert(SettlementEscrow.AttestationNotFound.selector);
        escrow.release(dealId, keccak256("no such attestation"));
    }

    function test_release_reverts_on_zero_uid() public {
        bytes32 dealId = _deposit();
        vm.expectRevert(SettlementEscrow.AttestationNotFound.selector);
        escrow.release(dealId, bytes32(0));
    }

    function test_release_reverts_on_wrong_schema() public {
        bytes32 dealId = _deposit();
        bytes32 otherSchema = registry.register(
            "bytes32 dealId, address payee, address token, uint256 amount, uint8 decision, bytes32 a, bytes32 b",
            ISchemaResolver(address(0)),
            true
        );
        bytes32 uid = _attestRaw(
            attester,
            otherSchema,
            address(escrow),
            deadline,
            _data(dealId, payee, address(usdc), AMOUNT, APPROVE)
        );
        vm.expectRevert(SettlementEscrow.AttestationWrongSchema.selector);
        escrow.release(dealId, uid);
    }

    function test_release_reverts_when_addressed_to_nobody() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attestRaw(
            attester,
            schemaUid,
            address(0),
            deadline,
            _data(dealId, payee, address(usdc), AMOUNT, APPROVE)
        );
        vm.expectRevert(SettlementEscrow.AttestationWrongRecipient.selector);
        escrow.release(dealId, uid);
    }

    function test_release_reverts_when_addressed_to_another_escrow() public {
        bytes32 dealId = _deposit();
        SettlementEscrow other = _newEscrow();
        bytes32 uid = _attestRaw(
            attester,
            schemaUid,
            address(other),
            deadline,
            _data(dealId, payee, address(usdc), AMOUNT, APPROVE)
        );
        vm.expectRevert(SettlementEscrow.AttestationWrongRecipient.selector);
        escrow.release(dealId, uid);
    }

    function test_release_reverts_on_untrusted_attester() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attestRaw(
            stranger,
            schemaUid,
            address(escrow),
            deadline,
            _data(dealId, payee, address(usdc), AMOUNT, APPROVE)
        );
        vm.expectRevert(SettlementEscrow.AttesterNotTrusted.selector);
        escrow.release(dealId, uid);
    }

    function test_buyer_cannot_approve_their_own_deal() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attestRaw(
            buyer,
            schemaUid,
            address(escrow),
            deadline,
            _data(dealId, payee, address(usdc), AMOUNT, APPROVE)
        );
        vm.expectRevert(SettlementEscrow.AttesterNotTrusted.selector);
        escrow.release(dealId, uid);
    }

    function test_untrusting_an_attester_invalidates_its_outstanding_decisions() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attest(dealId, APPROVE);
        vm.prank(owner);
        escrow.setAttester(attester, false);

        vm.expectRevert(SettlementEscrow.AttesterNotTrusted.selector);
        escrow.release(dealId, uid);
    }

    function test_release_reverts_on_revoked_attestation() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attest(dealId, APPROVE);
        _revoke(uid);
        vm.expectRevert(SettlementEscrow.AttestationRevoked.selector);
        escrow.release(dealId, uid);
    }

    function test_release_reverts_on_expired_attestation() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attestRaw(
            attester,
            schemaUid,
            address(escrow),
            uint64(block.timestamp + 1 hours),
            _data(dealId, payee, address(usdc), AMOUNT, APPROVE)
        );
        vm.warp(block.timestamp + 1 hours);
        vm.expectRevert(SettlementEscrow.AttestationExpired.selector);
        escrow.release(dealId, uid);
    }

    function test_release_reverts_on_attestation_made_before_the_deposit() public {
        bytes32 dealId = escrow.computeDealId(buyer, SALT);
        bytes32 uid = _attest(dealId, APPROVE);
        vm.warp(block.timestamp + 1);
        _deposit();

        vm.expectRevert(SettlementEscrow.AttestationPredatesDeposit.selector);
        escrow.release(dealId, uid);
    }

    function test_release_reverts_on_short_data() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attestRaw(
            attester,
            schemaUid,
            address(escrow),
            deadline,
            abi.encode(dealId, payee, address(usdc), AMOUNT, APPROVE)
        );
        vm.expectRevert(SettlementEscrow.AttestationMalformed.selector);
        escrow.release(dealId, uid);
    }

    function test_release_reverts_on_long_data() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attestRaw(
            attester,
            schemaUid,
            address(escrow),
            deadline,
            abi.encode(
                dealId, payee, address(usdc), AMOUNT, APPROVE, POLICY_HASH, RECORD_HASH, uint256(1)
            )
        );
        vm.expectRevert(SettlementEscrow.AttestationMalformed.selector);
        escrow.release(dealId, uid);
    }

    function test_release_reverts_on_decision_for_another_deal() public {
        bytes32 dealId = _deposit();
        bytes32 uid =
            _attestFields(keccak256("another deal"), payee, address(usdc), AMOUNT, APPROVE);
        vm.expectRevert(SettlementEscrow.AttestationDealMismatch.selector);
        escrow.release(dealId, uid);
    }

    function test_release_reverts_on_payee_mismatch() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attestFields(dealId, stranger, address(usdc), AMOUNT, APPROVE);
        vm.expectRevert(SettlementEscrow.AttestationPayeeMismatch.selector);
        escrow.release(dealId, uid);
    }

    function test_release_reverts_on_token_mismatch() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attestFields(dealId, payee, address(0xBEEF), AMOUNT, APPROVE);
        vm.expectRevert(SettlementEscrow.AttestationTokenMismatch.selector);
        escrow.release(dealId, uid);
    }

    function test_release_reverts_on_amount_mismatch() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attestFields(dealId, payee, address(usdc), AMOUNT - 1, APPROVE);
        vm.expectRevert(SettlementEscrow.AttestationAmountMismatch.selector);
        escrow.release(dealId, uid);
    }

    function test_release_reverts_on_reject_decision() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attest(dealId, REJECT);
        vm.expectRevert(SettlementEscrow.AttestationDecisionMismatch.selector);
        escrow.release(dealId, uid);
    }

    function test_release_reverts_on_unknown_decision_codes() public {
        bytes32 dealId = _deposit();
        bytes32 zero = _attest(dealId, 0);
        bytes32 three = _attest(dealId, 3);
        vm.expectRevert(SettlementEscrow.AttestationDecisionMismatch.selector);
        escrow.release(dealId, zero);
        vm.expectRevert(SettlementEscrow.AttestationDecisionMismatch.selector);
        escrow.release(dealId, three);
    }

    function test_delisting_a_token_does_not_trap_open_deals() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attest(dealId, APPROVE);
        vm.prank(owner);
        escrow.setToken(address(usdc), false);
        escrow.release(dealId, uid);
        assertEq(usdc.balanceOf(payee), AMOUNT);
    }

    // ---- refund --------------------------------------------------------

    function test_refund_after_deadline_needs_no_attestation() public {
        bytes32 dealId = _deposit();
        uint256 buyerBefore = usdc.balanceOf(buyer);
        vm.warp(deadline);

        vm.expectEmit(true, true, false, true);
        emit SettlementRefunded(dealId, buyer, AMOUNT, bytes32(0));
        vm.prank(buyer);
        escrow.refund(dealId, bytes32(0));

        assertEq(usdc.balanceOf(buyer), buyerBefore + AMOUNT);
        assertEq(uint8(escrow.getDeal(dealId).status), uint8(SettlementEscrow.DealStatus.Refunded));
    }

    function test_refund_before_deadline_without_attestation_reverts() public {
        bytes32 dealId = _deposit();
        vm.warp(deadline - 1);
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.DeadlineNotReached.selector);
        escrow.refund(dealId, bytes32(0));
    }

    function test_refund_before_deadline_on_a_reject_decision() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attest(dealId, REJECT);
        uint256 buyerBefore = usdc.balanceOf(buyer);

        vm.expectEmit(true, true, false, true);
        emit SettlementRefunded(dealId, buyer, AMOUNT, uid);
        vm.prank(buyer);
        escrow.refund(dealId, uid);

        assertEq(usdc.balanceOf(buyer), buyerBefore + AMOUNT);
        assertEq(usdc.balanceOf(payee), 0);
    }

    function test_refund_only_buyer() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attest(dealId, REJECT);
        vm.prank(stranger);
        vm.expectRevert(SettlementEscrow.CallerNotBuyer.selector);
        escrow.refund(dealId, uid);

        vm.warp(deadline);
        vm.prank(payee);
        vm.expectRevert(SettlementEscrow.CallerNotBuyer.selector);
        escrow.refund(dealId, bytes32(0));
    }

    function test_refund_unknown_deal_reverts() public {
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.DealNotOpen.selector);
        escrow.refund(keccak256("nope"), bytes32(0));
    }

    function test_refund_twice_reverts() public {
        bytes32 dealId = _deposit();
        vm.warp(deadline);
        vm.startPrank(buyer);
        escrow.refund(dealId, bytes32(0));
        vm.expectRevert(SettlementEscrow.DealNotOpen.selector);
        escrow.refund(dealId, bytes32(0));
        vm.stopPrank();
    }

    function test_refund_after_release_reverts() public {
        bytes32 dealId = _deposit();
        escrow.release(dealId, _attest(dealId, APPROVE));
        vm.warp(deadline);
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.DealNotOpen.selector);
        escrow.refund(dealId, bytes32(0));
    }

    function test_approve_decision_cannot_be_used_to_refund_early() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attest(dealId, APPROVE);
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.AttestationDecisionMismatch.selector);
        escrow.refund(dealId, uid);
    }

    /// @dev The v1 escrow accepted any rejection that named the deal id. A buyer
    ///      could ask for a decision about a payee of their choosing, get a
    ///      REJECT, and walk away before the deadline.
    function test_selfserve_rejection_about_another_payee_does_not_refund() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attestFields(dealId, stranger, address(usdc), AMOUNT, REJECT);
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.AttestationPayeeMismatch.selector);
        escrow.refund(dealId, uid);
    }

    function test_refund_reverts_on_revoked_rejection() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attest(dealId, REJECT);
        _revoke(uid);
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.AttestationRevoked.selector);
        escrow.refund(dealId, uid);
    }

    function test_refund_reverts_on_expired_rejection() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attestRaw(
            attester,
            schemaUid,
            address(escrow),
            uint64(block.timestamp + 1 hours),
            _data(dealId, payee, address(usdc), AMOUNT, REJECT)
        );
        vm.warp(block.timestamp + 1 hours);
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.AttestationExpired.selector);
        escrow.refund(dealId, uid);
    }

    function test_refund_reverts_on_rejection_by_untrusted_attester() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attestRaw(
            buyer,
            schemaUid,
            address(escrow),
            deadline,
            _data(dealId, payee, address(usdc), AMOUNT, REJECT)
        );
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.AttesterNotTrusted.selector);
        escrow.refund(dealId, uid);
    }

    function test_refund_reverts_on_rejection_under_wrong_schema() public {
        bytes32 dealId = _deposit();
        bytes32 otherSchema = registry.register("bytes32 dealId", ISchemaResolver(address(0)), true);
        bytes32 uid = _attestRaw(
            attester,
            otherSchema,
            address(escrow),
            deadline,
            _data(dealId, payee, address(usdc), AMOUNT, REJECT)
        );
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.AttestationWrongSchema.selector);
        escrow.refund(dealId, uid);
    }

    function test_refund_reverts_on_rejection_addressed_elsewhere() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attestRaw(
            attester,
            schemaUid,
            stranger,
            deadline,
            _data(dealId, payee, address(usdc), AMOUNT, REJECT)
        );
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.AttestationWrongRecipient.selector);
        escrow.refund(dealId, uid);
    }

    function test_refund_reverts_on_rejection_for_another_deal() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attestFields(keccak256("another deal"), payee, address(usdc), AMOUNT, REJECT);
        vm.prank(buyer);
        vm.expectRevert(SettlementEscrow.AttestationDealMismatch.selector);
        escrow.refund(dealId, uid);
    }

    function test_refund_reverts_on_rejection_with_token_or_amount_mismatch() public {
        bytes32 dealId = _deposit();
        bytes32 wrongToken = _attestFields(dealId, payee, address(0xBEEF), AMOUNT, REJECT);
        bytes32 wrongAmount = _attestFields(dealId, payee, address(usdc), AMOUNT + 1, REJECT);
        vm.startPrank(buyer);
        vm.expectRevert(SettlementEscrow.AttestationTokenMismatch.selector);
        escrow.refund(dealId, wrongToken);
        vm.expectRevert(SettlementEscrow.AttestationAmountMismatch.selector);
        escrow.refund(dealId, wrongAmount);
        vm.stopPrank();
    }

    function test_after_the_deadline_only_the_refund_path_is_open() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attestRaw(
            attester,
            schemaUid,
            address(escrow),
            0,
            _data(dealId, payee, address(usdc), AMOUNT, APPROVE)
        );
        vm.warp(deadline + 1);

        vm.expectRevert(SettlementEscrow.DeadlinePassed.selector);
        escrow.release(dealId, uid);

        vm.prank(buyer);
        escrow.refund(dealId, bytes32(0));
        assertEq(usdc.balanceOf(payee), 0);
        assertEq(usdc.balanceOf(address(escrow)), 0);
    }

    // ---- cross-deployment replay ---------------------------------------

    function test_decision_cannot_be_replayed_on_another_escrow() public {
        bytes32 dealId = _deposit();
        bytes32 uid = _attest(dealId, APPROVE);

        SettlementEscrow other = _newEscrow();
        vm.startPrank(buyer);
        usdc.approve(address(other), AMOUNT);
        bytes32 otherDeal = other.deposit(SALT, payee, address(usdc), AMOUNT, deadline);
        vm.stopPrank();

        assertTrue(otherDeal != dealId);
        vm.expectRevert(SettlementEscrow.AttestationWrongRecipient.selector);
        other.release(otherDeal, uid);
    }

    // ---- fuzz ----------------------------------------------------------

    function testFuzz_release_pays_exactly_the_deposit(uint128 rawAmount, bytes32 salt) public {
        uint256 amount = bound(uint256(rawAmount), 1, 1e30);
        usdc.mint(buyer, amount);
        vm.prank(buyer);
        bytes32 dealId = escrow.deposit(salt, payee, address(usdc), amount, deadline);
        bytes32 uid = _attestFields(dealId, payee, address(usdc), amount, APPROVE);

        escrow.release(dealId, uid);
        assertEq(usdc.balanceOf(payee), amount);
        assertEq(usdc.balanceOf(address(escrow)), 0);
    }

    function testFuzz_decision_with_any_other_amount_never_settles(uint128 rawAmount, bool reject)
        public
    {
        vm.assume(uint256(rawAmount) != AMOUNT);
        bytes32 dealId = _deposit();
        bytes32 uid =
            _attestFields(dealId, payee, address(usdc), rawAmount, reject ? REJECT : APPROVE);

        vm.expectRevert(SettlementEscrow.AttestationAmountMismatch.selector);
        if (reject) {
            vm.prank(buyer);
            escrow.refund(dealId, uid);
        } else {
            escrow.release(dealId, uid);
        }
    }

    function testFuzz_refund_without_decision_opens_exactly_at_the_deadline(uint32 offset) public {
        bytes32 dealId = _deposit();
        vm.warp(uint256(deadline) - 1 days + offset);

        vm.prank(buyer);
        if (offset < 1 days) {
            vm.expectRevert(SettlementEscrow.DeadlineNotReached.selector);
            escrow.refund(dealId, bytes32(0));
        } else {
            escrow.refund(dealId, bytes32(0));
            assertEq(usdc.balanceOf(address(escrow)), 0);
        }
    }
}
