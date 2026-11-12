// Copy the published example records and the public deployment descriptor
// from the repository into public/, so the static pages can load them.
import {cpSync, existsSync, mkdirSync, readdirSync, rmSync, writeFileSync} from "node:fs";
import {dirname, join} from "node:path";
import {fileURLToPath} from "node:url";

const web = join(dirname(fileURLToPath(import.meta.url)), "..");
const repo = join(web, "..", "..");
const out = join(web, "public", "data");

rmSync(out, {recursive: true, force: true});
mkdirSync(join(out, "records"), {recursive: true});

const index = [];
const examples = join(repo, "examples", "records");
if (existsSync(examples)) {
  for (const network of readdirSync(examples, {withFileTypes: true})) {
    if (!network.isDirectory()) continue;
    for (const file of readdirSync(join(examples, network.name))) {
      if (!file.endsWith(".json")) continue;
      const name = `${network.name}--${file}`;
      cpSync(join(examples, network.name, file), join(out, "records", name));
      index.push({network: network.name, file: name, label: file.replace(/\.json$/, "")});
    }
  }
}
writeFileSync(join(out, "records", "index.json"), JSON.stringify(index, null, 2) + "\n");

const deployment = join(repo, "deployments", "base-sepolia.json");
if (existsSync(deployment)) cpSync(deployment, join(out, "base-sepolia.json"));

console.log(`[sync-public] ${index.length} example record(s)` +
  (existsSync(deployment) ? ", public deployment descriptor" : ", no public deployment yet"));
