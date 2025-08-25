const path = require('path');

module.exports = {
  entry: './src/index.tsx',
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: 'bundle.js',
    publicPath: '/',
    clean: true
  },
  devtool: 'source-map',
  resolve: { extensions: ['.ts', '.tsx', '.js'] },
  module: {
    rules: [
      { test: /\.tsx?$/, use: 'ts-loader', exclude: /node_modules/ }
    ]
  },
  devServer: {
    static: path.join(__dirname, 'public'),
    port: 5173,
    hot: true,
    historyApiFallback: true
  }
};
