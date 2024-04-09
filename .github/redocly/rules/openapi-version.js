module.exports = checkOpenapiVersion;

function checkOpenapiVersion(options) {
  return {
    Root: {
      enter(operation, { report, location }) {
        if (operation.openapi !== options.version) {
          report({
            message: `OpenAPI version ${options.version} must be used.`,
            location: location.child(['openapi']).key(),
          });
        }
      },
    }
  };
}