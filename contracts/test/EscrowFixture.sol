// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.26;

import {Test} from "forge-std/Test.sol";

import {EAS} from "@eas/EAS.sol";
import {
    AttestationRequest,
    AttestationRequestData,
    RevocationRequest,
    RevocationRequestData
} from "@eas/IEAS.sol";
import {ISchemaRegistry} from "@eas/ISchemaRegistry.sol";
import {SchemaRegistry} from "@eas/SchemaRegistry.sol";
import {ISchemaResolver} from "@eas/resolver/ISchemaResolver.sol";

import {MockUSDC} from "../src/MockUSDC.sol";
import {SettlementEscrow} from "../src/SettlementEscrow.sol";

/// @notice Deploys the real EAS contracts, registers the published
///         `SettlementDecision` schema and wires one escrow. Tests attest
///         through EAS itself, not through a mock.
abstract contract EscrowFixture is Test {
    /// @dev UID of the schema in spec/eas-schema.txt (resolver zero, revocable).
    bytes32 internal constant PUBLISHED_SCHEMA_UID =
        0x1a86145e70ac5055683604a56201574b2c9edf0512ad08fc1368a9e7cb565135;

    uint8 internal constant APPROVE = 1;
    uint8 internal constant REJECT = 2;

    uint256 internal constant AMOUNT = 580e6;
    bytes32 internal constant SALT = keccak256("deal-1");
    bytes32 internal constant POLICY_HASH = keccak256("policy");
    bytes32 internal constant RECORD_HASH = keccak256("record");

    SchemaRegistry internal registry;
    EAS internal eas;
    SettlementEscrow internal escrow;
    MockUSDC internal usdc;
    bytes32 internal schemaUid;
    uint64 internal deadline;

    address internal owner = makeAddr("owner");
    address internal attester = makeAddr("attester");
    address internal buyer = makeAddr("buyer");
    address internal payee = makeAddr("payee");
    address internal stranger = makeAddr("stranger");

    function _deployFixture() internal {
        vm.warp(1_780_000_000);
        registry = new SchemaRegistry();
        eas = new EAS(ISchemaRegistry(address(registry)));
        schemaUid = registry.register(
            vm.readFile("../spec/eas-schema.txt"), ISchemaResolver(address(0)), true
        );
        usdc = new MockUSDC();
        escrow = _newEscrow();

        usdc.mint(buyer, 10_000e6);
        vm.prank(buyer);
        usdc.approve(address(escrow), type(uint256).max);
        deadline = uint64(block.timestamp + 1 days);
    }

    function _newEscrow() internal returns (SettlementEscrow) {
        address[] memory tokens = new address[](1);
        tokens[0] = address(usdc);
        address[] memory attesters = new address[](1);
        attesters[0] = attester;
        return new SettlementEscrow(address(eas), schemaUid, owner, tokens, attesters);
    }

    function _deposit() internal returns (bytes32 dealId) {
        vm.prank(buyer);
        dealId = escrow.deposit(SALT, payee, address(usdc), AMOUNT, deadline);
    }

    function _data(bytes32 dealId, address toPayee, address token, uint256 amount, uint8 decision)
        internal
        pure
        returns (bytes memory)
    {
        return abi.encode(dealId, toPayee, token, amount, decision, POLICY_HASH, RECORD_HASH);
    }

    function _attestRaw(
        address from,
        bytes32 schema,
        address recipient,
        uint64 expiration,
        bytes memory data
    ) internal returns (bytes32 uid) {
        vm.prank(from);
        uid = eas.attest(
            AttestationRequest({
                schema: schema,
                data: AttestationRequestData({
                    recipient: recipient,
                    expirationTime: expiration,
                    revocable: true,
                    refUID: bytes32(0),
                    data: data,
                    value: 0
                })
            })
        );
    }

    /// @dev A well-formed decision by the trusted attester about the fixture deal.
    function _attest(bytes32 dealId, uint8 decision) internal returns (bytes32) {
        return _attestRaw(
            attester,
            schemaUid,
            address(escrow),
            deadline,
            _data(dealId, payee, address(usdc), AMOUNT, decision)
        );
    }

    /// @dev A decision by the trusted attester with caller-chosen deal fields.
    function _attestFields(
        bytes32 dealId,
        address toPayee,
        address token,
        uint256 amount,
        uint8 decision
    ) internal returns (bytes32) {
        return _attestRaw(
            attester,
            schemaUid,
            address(escrow),
            deadline,
            _data(dealId, toPayee, token, amount, decision)
        );
    }

    function _revoke(bytes32 uid) internal {
        vm.prank(attester);
        eas.revoke(
            RevocationRequest({
                schema: schemaUid, data: RevocationRequestData({uid: uid, value: 0})
            })
        );
    }
}
