// usage: node format_schema.js <path_to_file>

const fs = require("fs");
const { parseYaml, stringifyYaml } = require("@redocly/openapi-core");

const reorder_schema = (root) => {
    const { title, summary, description, $ref, type, format, required, properties, enum: e, minimum, minLength, maximum, maxLength, pattern, example, examples, ...rest } = root;

    return {
        title,
        summary,
        description,
        $ref,
        type,
        format,
        required,
        properties,
        enum: e,
        minimum,
        minLength,
        maximum,
        maxLength,
        pattern,
        example,
        examples,
        ...rest,
    };
};

const reorder_required = (required) => {
    return required.slice().sort();
};

const reorder_properties = (properties, required = []) => {
    const requiredProps = [];
    const optionalProps = [];

    Object.keys(properties).forEach((key) => {
        if (required.includes(key)) {
            requiredProps.push(key);
        } else {
            optionalProps.push(key);
        }
    });

    requiredProps.sort();
    optionalProps.sort();

    const sortedProperties = {};
    [...requiredProps, ...optionalProps].forEach((key) => {
        sortedProperties[key] = properties[key];
    });

    return sortedProperties;
};

const fileName = process.argv[2];
if (!fileName) {
    console.error("Usage: node " + process.argv[1] + " <templateName>");
    process.exit(1);
}
const content = fs.readFileSync(fileName, "utf8");
let sort = parseYaml(content);
sort = reorder_schema(sort);
if (sort.required) {
    sort.required = reorder_required(sort.required);
}
if (sort.properties) {
    sort.properties = reorder_properties(sort.properties, sort.required);
}
fs.writeFileSync(fileName, stringifyYaml(sort, {'lineWidth': -1}));
