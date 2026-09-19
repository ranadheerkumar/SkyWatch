const fs = require("node:fs/promises");
const path = require("node:path");

const nextDir = path.join(process.cwd(), ".next");

async function removeWithRetries(targetPath, retries = 5, delayMs = 350) {
  for (let attempt = 1; attempt <= retries; attempt += 1) {
    try {
      await fs.rm(targetPath, { recursive: true, force: true });
      return;
    } catch (error) {
      const code = error && error.code ? String(error.code) : "UNKNOWN";
      const retriable = code === "EBUSY" || code === "EPERM" || code === "EINVAL" || code === "ENOTEMPTY";
      if (!retriable || attempt === retries) {
        throw error;
      }
      await new Promise((resolve) => setTimeout(resolve, delayMs * attempt));
    }
  }
}

async function main() {
  await removeWithRetries(nextDir);
}

main().catch((error) => {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`Failed to clean .next directory: ${message}`);
  process.exit(1);
});
