let data = "";
process.stdin.on("data", (chunk) => (data += chunk));
process.stdin.on("end", () => {
  let input;
  try {
    input = JSON.parse(data);
  } catch (e) {
    process.exit(0);
  }
  const toolInput = input.tool_input || {};
  const targets = [toolInput.file_path, toolInput.path, toolInput.command]
    .filter(Boolean)
    .join(" ");
  if (/(^|[\\/\s])\.env($|[^.\w])/.test(targets)) {
    console.log(
      JSON.stringify({
        hookSpecificOutput: {
          hookEventName: "PreToolUse",
          permissionDecision: "deny",
          permissionDecisionReason:
            "Access to .env is blocked by project policy (contains secrets).",
        },
      }),
    );
  }
  process.exit(0);
});
