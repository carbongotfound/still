// swift-tools-version:5.9
import PackageDescription

let package = Package(
 name: "Still",
 platforms: [.macOS(.v12)],
 // Sparkle installs updates (sparkle-project.org). Pinned: a new version is a reviewed change, not a silent one.
 dependencies: [.package(url: "https://github.com/sparkle-project/Sparkle", exact: "2.10.1")],
 targets: [.executableTarget(name: "Still", dependencies: [.product(name: "Sparkle", package: "Sparkle")], path: "Sources/Still")]
)
