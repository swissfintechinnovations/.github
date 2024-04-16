const checkObjectOrder = require('./rules/root-object-order');
const checkOpenapiVersion = require('./rules/openapi-version');
const infoStructure = require('./rules/info-content');
const checkExternalDocs = require('./rules/external-docs');
const checkBasepath = require('./rules/base-path');
const componentsOrder = require('./rules/component-order');
const checkParameterOrder = require('./rules/parameter-name-order');
const checkParameterObjectOrder = require('./rules/parameter-object-order')

const infoDescription = require('./rules/info-description');
const tagDescription = require('./rules/tag-description');
const parameterDescription = require('./rules/parameter-description');
const checkPathParameter = require('./rules/path-parameter');

const checkHeaderParameter = require('./rules/header-parameter');
const checkQueryParameter = require('./rules/query-parameter');

module.exports = {
  id: 'sfti',
  rules: {
    oas3: {
      'root-object-order' : checkObjectOrder,
      'openapi-version': checkOpenapiVersion,
      'info-content' : infoStructure,
      'external-docs' : checkExternalDocs,
      'base-path' : checkBasepath,
      'component-order' : componentsOrder,
      'parameter-name-order' : checkParameterOrder,
      'parameter-object-order' : checkParameterObjectOrder,
      // 'use-ref-when-used-multiple-times' : checkObjectRedundancy, // TODO object is used more than once WARN

      'info-description' : infoDescription,
      'tag-description' : tagDescription,
      'parameter-description' : parameterDescription,

      'path-parameter' : checkPathParameter,
      'header-parameter' : checkHeaderParameter,
      'query-parameter' : checkQueryParameter,
    }
  }
};
