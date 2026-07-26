/**
 * electron-builder 配置。
 * 当前阶段只配置开发用，正式打包后续优化。
 */
export = {
  appId: "io.lumio.desktop",
  productName: "Lumio",
  directories: {
    output: "release",
  },
  files: ["dist/**/*", "dist-electron/**/*"],
  // TODO: 打包 Python 后端（PyInstaller）+ 内置 Python runtime
  // extraResources: [
  //   { from: "../python-dist", to: "python-backend" }
  // ],
  win: {
    target: ["nsis"],
  },
  mac: {
    target: ["dmg"],
  },
  linux: {
    target: ["AppImage"],
  },
};
