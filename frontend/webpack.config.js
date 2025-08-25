const path = require("path");
const webpack = require("webpack");

module.exports = (env) => ({
  entry: "./src/index.tsx",
  output: {
    path: path.resolve(__dirname, "dist"),
    filename: "bundle.js",
    publicPath: "/",
    clean: true,
  },
  devtool: "source-map",
  resolve: { extensions: [".ts", ".tsx", ".js"] },
  module: {
    rules: [
      { test: /\.tsx?$/, use: "ts-loader", exclude: /node_modules/ },
      { test: /\.css$/, use: ["style-loader", "css-loader"] },
    ],
  },
  devServer: {
    static: path.join(__dirname, "public"),
    port: Number(process.env.FRONTEND_DEV_PORT || 5173),
    hot: true,
    historyApiFallback: true,
  },
  plugins: [
    new webpack.DefinePlugin({
      "process.env.VOICE_AGENT_URL": JSON.stringify(
        process.env.VOICE_AGENT_URL || ""
      ),
      "process.env.MSG_PROXY_URL": JSON.stringify(
        process.env.MSG_PROXY_URL || ""
      ),
      "process.env.ORCHESTRATOR_URL": JSON.stringify(
        process.env.ORCHESTRATOR_URL || ""
      ),
    }),
  ],
});
