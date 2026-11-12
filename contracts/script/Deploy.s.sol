// SPDX-License-Identifier: Apache-2.0
pragma solidity ^0.8.26;

import {Script, console2} from "forge-std/Script.sol";

import {ISchemaRegistry, SchemaRecord} from "@eas/ISchemaRegistry.sol";
import {ISchemaResolver} from "@eas/resolver/ISchemaResolver.sol";

import {MockUSDC} from "../src/MockUSDC.sol";
import {SettlementEscrow} from "../src/SettlementEscrow.sol";

/// @title Deploy
/// @notice Registers the `SettlementDecision` schema if the chain does not
///         have it yet, deploys a demo token unless one is supplied, and
///         deploys the escrow. The deployer receives no privileges: the owner
///         and the attester are separate addresses passed in.
///
/// Environment:
///   DEPLOYER_PRIVATE_KEY         key that pays for the deployment
///   ESCROW_OWNER_ADDRESS         admin of the attester and token lists
///   ATTESTER_ADDRESS             attester trusted from the start
///   SETTLEMENT_TOKEN_ADDRESS     optional; existing ERC-20 to allow instead of a new MockUSDC
///   EAS_ADDRESS                  optional; defaults to the OP-stack predeploy
///   EAS_SCHEMA_REGISTRY_ADDRESS  optional; defaults to the OP-stack predeploy
///
/// Usage:
///   forge script script/Deploy.s.sol --rpc-url $RPC_URL --broadcast
contract Deploy is Script {
    address internal constant EAS_PREDEPLOY = 0x4200000000000000000000000000000000000021;
    address internal constant REGISTRY_PREDEPLOY = 0x4200000000000000000000000000000000000020;

    function run() external {
        uint256 deployerKey = vm.envUint("DEPLOYER_PRIVATE_KEY");
        address owner = vm.envAddress("ESCROW_OWNER_ADDRESS");
        address attester = vm.envAddress("ATTESTER_ADDRESS");
        address eas = vm.envOr("EAS_ADDRESS", EAS_PREDEPLOY);
        ISchemaRegistry registry =
            ISchemaRegistry(vm.envOr("EAS_SCHEMA_REGISTRY_ADDRESS", REGISTRY_PREDEPLOY));
        address token = vm.envOr("SETTLEMENT_TOKEN_ADDRESS", address(0));

        require(owner != address(0), "Deploy: owner is zero");
        require(attester != address(0), "Deploy: attester is zero");
        require(owner != attester, "Deploy: owner and attester must differ");

        string memory schema = vm.readFile("../spec/eas-schema.txt");
        bytes32 schemaUid = keccak256(abi.encodePacked(schema, address(0), true));

        vm.startBroadcast(deployerKey);

        SchemaRecord memory existing = registry.getSchema(schemaUid);
        if (existing.uid == bytes32(0)) {
            bytes32 registered = registry.register(schema, ISchemaResolver(address(0)), true);
            require(registered == schemaUid, "Deploy: unexpected schema uid");
        }

        if (token == address(0)) {
            token = address(new MockUSDC());
        }

        address[] memory tokens = new address[](1);
        tokens[0] = token;
        address[] memory attesters = new address[](1);
        attesters[0] = attester;
        SettlementEscrow escrow = new SettlementEscrow(eas, schemaUid, owner, tokens, attesters);

        vm.stopBroadcast();

        console2.log("CHAIN_ID=%s", block.chainid);
        console2.log("EAS_ADDRESS=%s", eas);
        console2.log("SETTLEMENT_TOKEN_ADDRESS=%s", token);
        console2.log("SETTLEMENT_ESCROW_ADDRESS=%s", address(escrow));
        console2.log("ESCROW_OWNER_ADDRESS=%s", owner);
        console2.log("ATTESTER_ADDRESS=%s", attester);
        console2.log("EAS_SCHEMA_UID=%s", vm.toString(schemaUid));
    }
}
