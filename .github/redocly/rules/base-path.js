module.exports = checkBasepath;

function checkBasepath(options) {
  return {
    Root: {
      enter(operation, { report, location, type }) {
        if (operation.basePath === undefined) {
          report({
            message: `The basePath object must be present before tags object.`,
            location: { reportOnKey: true },
          });
        }
        else if (! operation.basePath.endsWith('/v'+operation.info.version.split('.')[0])) {
          report({
            message: `Base path must be aligned with Major version of API specification. Path must end with '/v[Major version]'`,
            location: location.child(['basePath']),
          });
        }
      },
    }
  };
}