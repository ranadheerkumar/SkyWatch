import { readFileSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const packagePath = resolve(root, "frontend", "package.json");
const lockPath = resolve(root, "frontend", "package-lock.json");
const packageRelativePath = "frontend/package.json";
const requireWorkingTreeBump = process.argv.includes("--require-bump");
const requireHistoryBump = process.argv.includes("--require-history-bump");
const semverPattern = /^(\d+)\.(\d+)\.(\d+)(?:-[0-9A-Za-z.-]+)?$/;

function readJson(path) {
  try {
    return JSON.parse(readFileSync(path, "utf8"));
  } catch (error) {
    throw new Error(`Unable to read ${path}: ${error instanceof Error ? error.message : String(error)}`);
  }
}

function parseVersion(version, label) {
  if (typeof version !== "string" || !semverPattern.test(version)) {
    throw new Error(`${label} must use Semantic Versioning MAJOR.MINOR.PATCH; received ${String(version)}`);
  }
  const match = version.match(semverPattern);
  return { text: version, major: Number(match[1]), minor: Number(match[2]), patch: Number(match[3]) };
}

function compareVersions(left, right) {
  return left.major - right.major || left.minor - right.minor || left.patch - right.patch;
}

function gitShow(ref) {
  try {
    return JSON.parse(execFileSync("git", ["show", `${ref}:${packageRelativePath}`], { cwd: root, encoding: "utf8" }));
  } catch {
    return null;
  }
}

const packageMetadata = readJson(packagePath);
const lockMetadata = readJson(lockPath);
const lockRootPackage = lockMetadata.packages?.[""];
const currentVersion = parseVersion(packageMetadata.version, "frontend/package.json version");
const lockVersion = parseVersion(lockMetadata.version, "frontend/package-lock.json version");
const lockRootVersion = parseVersion(lockRootPackage?.version, "frontend/package-lock.json root version");

if (packageMetadata.name !== lockMetadata.name || packageMetadata.name !== lockRootPackage?.name) {
  throw new Error("frontend/package.json and package-lock.json package names must match");
}
if (currentVersion.text !== lockVersion.text || currentVersion.text !== lockRootVersion.text) {
  throw new Error(`Version mismatch: package.json=${currentVersion.text}, package-lock.json=${lockVersion.text}, lock root=${lockRootVersion.text}`);
}

if (requireWorkingTreeBump) {
  const previousMetadata = gitShow("HEAD");
  if (previousMetadata) {
    const previousVersion = parseVersion(previousMetadata.version, "HEAD version");
    if (compareVersions(currentVersion, previousVersion) <= 0) {
      throw new Error(`Working tree version ${currentVersion.text} must be greater than HEAD version ${previousVersion.text}`);
    }
  }
}

if (requireHistoryBump) {
  const previousMetadata = gitShow("HEAD^");
  const headMetadata = gitShow("HEAD") ?? packageMetadata;
  if (previousMetadata) {
    const previousVersion = parseVersion(previousMetadata.version, "parent commit version");
    const headVersion = parseVersion(headMetadata.version, "HEAD version");
    if (compareVersions(headVersion, previousVersion) <= 0) {
      throw new Error(`Pushed commit version ${headVersion.text} must be greater than parent version ${previousVersion.text}`);
    }
    if (headVersion.text !== currentVersion.text) {
      throw new Error(`Checked out package version ${currentVersion.text} does not match HEAD version ${headVersion.text}`);
    }
  }
}

console.log(`version check: pass (${currentVersion.text})`);
