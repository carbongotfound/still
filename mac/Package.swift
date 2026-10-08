// swift-tools-version:5.9
import PackageDescription

let package = Package(
 name: "Still",
 platforms: [.macOS(.v12)],
 targets: [.executableTarget(name: "Still", path: "Sources/Still")]
)
