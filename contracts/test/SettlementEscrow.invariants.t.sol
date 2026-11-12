// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.26;

import {Test} from "forge-std/Test.sol";

import {EAS} from "@eas/EAS.sol";
import {AttestationRequest, AttestationRequestData} from "@eas/IEAS.sol";

import {MockUSDC} from "../src/MockUSDC.sol";
import {SettlementEscrow} from "../src/SettlementEscrow.sol";
import {EscrowFixture} from "./EscrowFixture.sol";

/// @notice Drives the escrow with random deposits, decisions, releases,
///         refunds and time jumps, and keeps its own books.
contract EscrowHandler is Test {
    SettlementEscrow internal immutable escrow;
    MockUSDC internal immutable usdc;
    EAS internal immutable eas;
    bytes32 internal immutable schemaUid;
    address internal immutable attester;
    address internal immutable payee;

    address[] internal buyers;
    bytes32[] internal dealIds;
    uint256 internal saltCounter;

    uint256 public totalDeposited;
    uint256 public totalReleased;
    uint256 public totalRefunded;

    constructor(
        SettlementEscrow escrow_,
        MockUSDC usdc_,
        EAS eas_,
        bytes32 schemaUid_,
        address attester_,
        address payee_
    ) {
        escrow = escrow_;
        usdc = usdc_;
        eas = eas_;
        schemaUid = schemaUid_;
        attester = attester_;
        payee = payee_;
        for (uint256 i = 0; i < 3; ++i) {
            address buyer = makeAddr(string.concat("buyer-", vm.toString(i)));
            buyers.push(buyer);
            vm.prank(buyer);
            usdc.approve(address(escrow), type(uint256).max);
        }
    }

    function dealCount() external view returns (uint256) {
        return dealIds.length;
    }

    function openAmount() external view returns (uint256 sum) {
        for (uint256 i = 0; i < dealIds.length; ++i) {
            SettlementEscrow.Deal memory d = escrow.getDeal(dealIds[i]);
            if (d.status == SettlementEscrow.DealStatus.Open) sum += d.amount;
        }
    }

    function deposit(uint256 buyerSeed, uint256 amount, uint256 lifetime) external {
        address buyer = buyers[buyerSeed % buyers.length];
        amount = bound(amount, 1, 1e12);
        lifetime = bound(lifetime, 1 hours, 30 days);
        usdc.mint(buyer, amount);

        vm.prank(buyer);
        bytes32 dealId = escrow.deposit(
            bytes32(++saltCounter), payee, address(usdc), amount, uint64(block.timestamp + lifetime)
        );
        dealIds.push(dealId);
        totalDeposited += amount;
    }

    function release(uint256 dealSeed) external {
        (bytes32 dealId, SettlementEscrow.Deal memory d) = _pick(dealSeed);
        if (d.status != SettlementEscrow.DealStatus.Open || block.timestamp >= d.deadline) return;
        escrow.release(dealId, _decide(dealId, d, 1));
        totalReleased += d.amount;
    }

    function refundOnRejection(uint256 dealSeed) external {
        (bytes32 dealId, SettlementEscrow.Deal memory d) = _pick(dealSeed);
        if (d.status != SettlementEscrow.DealStatus.Open || block.timestamp >= d.deadline) return;
        bytes32 uid = _decide(dealId, d, 2);
        vm.prank(d.buyer);
        escrow.refund(dealId, uid);
        totalRefunded += d.amount;
    }

    function refundAfterDeadline(uint256 dealSeed) external {
        (bytes32 dealId, SettlementEscrow.Deal memory d) = _pick(dealSeed);
        if (d.status != SettlementEscrow.DealStatus.Open) return;
        if (block.timestamp < d.deadline) vm.warp(d.deadline);
        vm.prank(d.buyer);
        escrow.refund(dealId, bytes32(0));
        totalRefunded += d.amount;
    }

    function skipTime(uint256 seconds_) external {
        vm.warp(block.timestamp + bound(seconds_, 1, 3 days));
    }

    function _pick(uint256 seed)
        private
        view
        returns (bytes32 dealId, SettlementEscrow.Deal memory d)
    {
        if (dealIds.length == 0) return (bytes32(0), d);
        dealId = dealIds[seed % dealIds.length];
        d = escrow.getDeal(dealId);
    }

    function _decide(bytes32 dealId, SettlementEscrow.Deal memory d, uint8 decision)
        private
        returns (bytes32 uid)
    {
        vm.prank(attester);
        uid = eas.attest(
            AttestationRequest({
                schema: schemaUid,
                data: AttestationRequestData({
                    recipient: address(escrow),
                    expirationTime: d.deadline,
                    revocable: true,
                    refUID: bytes32(0),
                    data: abi.encode(
                        dealId, d.payee, d.token, d.amount, decision, bytes32(0), bytes32(0)
                    ),
                    value: 0
                })
            })
        );
    }
}

contract SettlementEscrowInvariants is EscrowFixture {
    EscrowHandler internal handler;

    function setUp() public {
        _deployFixture();
        handler = new EscrowHandler(escrow, usdc, eas, schemaUid, attester, payee);
        targetContract(address(handler));
    }

    /// @dev The escrow holds exactly the sum of its open deals: no deposit is
    ///      lost and nothing can be paid out twice.
    function invariant_balance_equals_open_deals() public view {
        assertEq(usdc.balanceOf(address(escrow)), handler.openAmount());
    }

    /// @dev Every deposited unit is either still held, released or refunded.
    function invariant_funds_are_conserved() public view {
        assertEq(
            handler.totalDeposited(),
            handler.totalReleased() + handler.totalRefunded() + usdc.balanceOf(address(escrow))
        );
    }

    /// @dev Releases reach the payee and nobody else.
    function invariant_payee_received_exactly_the_releases() public view {
        assertEq(usdc.balanceOf(payee), handler.totalReleased());
    }
}
