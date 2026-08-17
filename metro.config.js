const {getDefaultConfig, mergeConfig} = require('@react-native/metro-config');

/**
 * Metro configuration
 * https://facebook.github.io/metro/docs/configuration
 *
 * @type {import('metro-config').MetroConfig}
 */
const config = {
  resolver: {
    // prototypes/ holds standalone web prototypes with their own package.json and
    // node_modules (react-dom, etc.). Keep them out of the React Native module graph
    // so they cannot collide with this app's dependencies or be watched needlessly.
    blockList: /(^|[/\\])prototypes[/\\].*/,
  },
};

module.exports = mergeConfig(getDefaultConfig(__dirname), config);
