// usage: node autoformat_linelength.js <path_to_file>

const fs = require("fs");
const { parseYaml, stringifyYaml } = require("@redocly/openapi-core");

const fileName = process.argv[2];
const content = fs.readFileSync(fileName, "utf8");
let parsed = parseYaml(content);
fs.writeFileSync(fileName, stringifyYaml(parsed, {'lineWidth': 140}));