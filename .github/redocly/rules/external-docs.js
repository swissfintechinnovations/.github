module.exports = checkExternalDocs;

function checkExternalDocs(options) {
    return {
      ExternalDocs: {
        enter(operation, { report, location }) {
          if (operation.description !== 'Find out more about SFTI API specifications.') {
            report({
              message: `Use offical SFTI reference string.`,
              location: location.child(['description']),
              suggest: [ 'Find out more about SFTI API specifications.' ],
            });
          }
          if (operation.url !== 'https://www.common-api.ch') {
            report({
              message: `Use offical Common API url.`,
              location: location.child(['url']),
              suggest: [ 'https://www.common-api.ch' ],
            });
          }
        },
      }
    };
  }