// usage: node autoformat_spec.js <path_to_file>

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

    const sortObjectKeys = (obj) => {
        if (!obj) return obj;
        return Object.keys(obj)
            .sort()
            .reduce((sorted, key) => {
                sorted[key] = obj[key];
                return sorted;
            }, {});
    };

    return {
        // define components object order
        schemas: sortObjectKeys(schemas),
        responses: sortObjectKeys(responses),
        parameters: sortObjectKeys(parameters),
        examples: sortObjectKeys(examples),
        requestBodies: sortObjectKeys(requestBodies),
        headers: sortObjectKeys(headers),
        securitySchemes: sortObjectKeys(securitySchemes),
        links: sortObjectKeys(links),
        callbacks: sortObjectKeys(callbacks),
        pathItems: sortObjectKeys(pathItems),
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
fs.writeFileSync(fileName, stringifyYaml(reordered, {'lineWidth': 170}));
