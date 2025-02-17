// usage: node format_schema.js <path_to_file>

const fs = require("fs");
const { parseYaml, stringifyYaml } = require("@redocly/openapi-core");

const reorder_parameter = (root) => {
    const { in: i, name, description, required, schema, ...rest } = root;

    return {
        in: i,
        name,
        description,
        required,
        schema,
        ...rest,
    };
};

const fileName = process.argv[2];
if (!fileName) {
    console.error("Usage: node " + process.argv[1] + " <templateName>");
    process.exit(1);
}
const content = fs.readFileSync(fileName, "utf8");
let sort = parseYaml(content);
sort = reorder_parameter(sort);
fs.writeFileSync(fileName, stringifyYaml(sort));
