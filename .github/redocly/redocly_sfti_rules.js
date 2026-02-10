import checkSchemaName from './rules/data-types.js';

import checkObjectOrder from './rules/root-object-order.js';
import checkOpenapiVersion from './rules/openapi-version.js';
import infoStructure from './rules/info-content.js';
import checkExternalDocs from './rules/external-docs.js';
import componentsOrder from './rules/component-order.js';

import infoDescription from './rules/info-description.js';
import tagDescription from './rules/tag-description.js';
import parameterDescription from './rules/parameter-description.js';
import schemaDescription from './rules/schema-description.js';
import schemaPattern from './rules/schema-pattern.js';

import checkPathParameter from './rules/path-parameter.js';
import checkHeaderParameter from './rules/header-parameter.js';
import checkQueryParameter from './rules/query-parameter.js';
import checkTags from './rules/tags.js';

import ApiSchemaRequired from './decorators/api-schema-required.js';
import StripXApiLevel from './decorators/strip-x-api-level.js';

export default function sftiPlugin() {
  return {
    id: 'sfti',
    rules: {
      oas3: {
        'data-types': checkSchemaName,

        'root-object-order': checkObjectOrder,
        'openapi-version': checkOpenapiVersion,
        'info-content': infoStructure,
        'external-docs': checkExternalDocs,
        'component-order': componentsOrder,

        'info-description': infoDescription,
        'tag-description': tagDescription,
        'parameter-description': parameterDescription,
        'schema-description': schemaDescription,
        'schema-pattern': schemaPattern,

        'path-parameter': checkPathParameter,
        'header-parameter': checkHeaderParameter,
        'query-parameter': checkQueryParameter,
        'tag': checkTags,
      },
    },
    decorators: {
      oas3: {
        'schema-required': ApiSchemaRequired,
        'strip-x-api-level': StripXApiLevel,
      },
    },
  };
}
