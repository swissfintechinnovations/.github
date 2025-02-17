// usage: node reorder.js <path_to_file>

const fs = require("fs");
const { parseYaml, stringifyYaml } = require("@redocly/openapi-core");

const reorder_root = (root) => {
    const { openapi, info, jsonSchemaDialect, servers, paths, webhooks, components, security, tags, externalDocs, ...rest } = root;
    return {
        // define root object order
        openapi,
        info,
        servers,
        externalDocs,
        jsonSchemaDialect,
        tags,
        security,
        paths,
        webhooks,
        components,
        ...rest,
    };
};

const reorder_components = (components) => {
    const { schemas, responses, parameters, examples, requestBodies, headers, securitySchemes, links, callbacks, pathItems, ...rest } = components;
    return {
        // define components object order
        schemas,
        responses,
        parameters,
        examples,
        requestBodies,
        headers,
        securitySchemes,
        links,
        callbacks,
        pathItems,
        ...rest,
    };
};

const fileName = process.argv[2];
if (!fileName) {
    console.error("Usage: node " + process.argv[1] + " <fileName>");
    process.exit(1);
}
const content = fs.readFileSync(fileName, "utf8");
let reordered = parseYaml(content);
reordered = reorder_root(reordered);
reordered.components = reorder_components(reordered.components);
console.log(reordered)
fs.writeFileSync(fileName, stringifyYaml(reordered, {'lineWidth': 150}));
