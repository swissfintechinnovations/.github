// usage: node format_template.js <path_to_file>

const fs = require("fs");
const { parseYaml, stringifyYaml } = require("@redocly/openapi-core");

const sort_tags = (tags) => {
    if (tags && Array.isArray(tags)) {
        tags.sort((a, b) => a.name.localeCompare(b.name));
    }
    return tags;
};

const sort_methods = (paths) => {
    const methodOrder = ["get", "post", "patch", "put", "delete"];

    if (paths && typeof paths === "object") {
        for (const path in paths) {
            const methods = paths[path];
            const sortedMethods = {};

            Object.keys(methods)
                .sort((a, b) => {
                    const orderA = methodOrder.indexOf(a);
                    const orderB = methodOrder.indexOf(b);
                    return orderA - orderB;
                })
                .forEach((method) => {
                    sortedMethods[method] = methods[method];
                });

            paths[path] = sortedMethods;
        }
    }
    return paths;
};

const fileName = process.argv[2];
if (!fileName) {
    console.error("Usage: node " + process.argv[1] + " <templateName>");
    process.exit(1);
}
const content = fs.readFileSync(fileName, "utf8");
let sort = parseYaml(content);
sort.tags = sort_tags(sort.tags);
sort.paths = sort_methods(sort.paths);
fs.writeFileSync(fileName, stringifyYaml(sort, {'lineWidth': -1}));
