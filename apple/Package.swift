// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "WolfBox",
    platforms: [.macOS(.v14)],
    products: [.executable(name: "WolfBox", targets: ["WolfBox"])],
    targets: [
        .target(name: "WolfBoxCore"),
        .executableTarget(name: "WolfBox", dependencies: ["WolfBoxCore"], resources: [.process("Resources")]),
        .testTarget(name: "WolfBoxCoreTests", dependencies: ["WolfBoxCore"]),
        .testTarget(name: "WolfBoxAppTests", dependencies: ["WolfBox", "WolfBoxCore"])
    ]
)
