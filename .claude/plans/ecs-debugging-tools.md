# ECS Debugging Tools — MCP Extension Suite

## Context

Semi-automatic debugging loop using Claude Code + Unity MCP (`com.unity.ai.assistant@2.0`). Works for compilation errors; breaks down for Unity DOTS runtime issues where silent query misses and complex init ordering are the primary failure modes.

Pain points:
1. **Agent impatience**: queries Editor before compilation finishes after a rebuild
2. **Silent runtime failures**: systems skip work because an entity's archetype is missing a component — no error, nothing happens
3. **No runtime execution visibility**: static Mermaid system flow maps (component producers/consumers + usage tables) exist but runtime ordering and actual access patterns are not verifiable from within the debugging loop

This plan produces: (a) Unity C# MCP tools registered inside the Editor, (b) an external debugger MCP server for breakpoint-halted inspection, and (c) slash command skills encoding investigation procedures. Coplay (`CoplayDev/unity-mcp`) is replaced; its two used capabilities (`reflect_type`, `validate_csharp`) are ported with improvements.

All implementation follows **TDD red-green workflow**: tests written first, implementation written to make them pass.

---

## Architecture

### Registration Mechanism
All Unity-side tools use `[McpTool]` in `Unity.AI.MCP.Editor.ToolRegistry`. TypeCache auto-discovers at Editor startup. Async tools implement `IUnityMcpTool<TParams>`.

```csharp
[McpTool("tool_name", "Description")]
public class MyTool : IUnityMcpTool<MyParams>
{
    public Task<object> ExecuteAsync(MyParams p) { ... }
}
```

### Two-Server Split
- **In-Editor C# tools**: run inside the Unity Editor process — available when the Editor is NOT suspended at a debugger breakpoint
- **External debugger MCP server**: runs in a separate process, speaks to Unity's Mono soft debugger via TCP — available specifically when the Editor IS suspended at a breakpoint

---

## Layer 1: Unity C# Package

**Location**: `ecs-mcp-unity-package/` (UPM package; added to game project as local or git dependency)
**Namespace**: `Mordochor.EcsMcp.Editor`

### Tools

#### `wait_until_ready`
Blocks until `EditorApplication.isCompiling == false && !EditorApplication.isUpdating`. Uses `CompilationPipeline.compilationFinished` + `TaskCompletionSource`. Called by the agent after applying a fix, before checking if the fix worked.
```
Parameters: timeout_ms (int, default 30000)
Returns: { ready: bool, errors: int, warnings: int, elapsed_ms: int }
```

#### `run_and_capture_error`
The entry point for the debugging loop. Executes the full error-discovery sequence as a single blocking call:
1. Clears the console (`Debug.ClearDeveloperConsole()`) to discard stale errors
2. Ensures compilation is complete (internal `wait_until_ready`)
3. If compile errors exist → returns them immediately
4. If no compile errors: enables pause-on-error, enters play mode, listens for the first runtime error
5. Returns on first error or on timeout (success)

```
Parameters: timeout_ms (int, default 60000)
Returns: {
  errorType: "compile" | "runtime" | "none",
  messages: [{ type, message, stacktrace, file, line }]
}
```

*Implementation note: uses `Application.logMessageReceived` for runtime errors and reads compile errors from `CompilationPipeline.GetAssemblyMessages()`. Pause-on-error set via `PlayerSettings.pauseOnError = true` before entering play mode, restored after.*

#### `get_editor_state`
Quick snapshot before any tool call.
```
Returns: { isCompiling, isPlaying, isPaused, hasErrors, errorCount, activeScene }
```

#### `get_ecs_worlds`
Lists all `World` instances via `World.All`.
```
Returns: [{ worldName, systemCount, isDefault, isRunning }]
```

#### `get_system_execution_order`
Walks the `ComponentSystemGroup` hierarchy. Returns actual runtime ordering — the order systems are called each frame, not just declared attributes. Includes enabled state.
```
Parameters: worldName (string)
Returns: tree of { systemName, systemType, enabled, updateGroup, children[] }
```

#### `query_entities`
Queries `EntityManager` by component predicate.
- `hasAll`: must have all of these
- `hasAny`: must have at least one
- `missingAll`: must have none of these
- `withValue`: optional component+field value filter (for narrow queries)

```
Parameters: worldName, hasAll[], hasAny[], missingAll[], withValue?, limit (default 50)
Returns: [{ entityId, entityIndex, entityVersion, components[] }]
```

#### `get_entity_archetype`
Full component list for a specific entity ID.
```
Parameters: worldName, entityIndex, entityVersion
Returns: { entityId, components[], chunkIndex, archetypeHash }
```

#### `get_entity_journal`
Queries `EntityChangeJournal` for structural changes. Returns readable change log.

*Requires `UNITY_EDITOR` or `ENABLE_UNITY_COLLECTIONS_CHECKS`. Accessible via this tool when game is running or when paused via `EditorApplication.isPaused`. When suspended at a debugger breakpoint, use `get_journal_at_breakpoint` from Layer 2 instead.*
```
Parameters: worldName, entityIndex?, entityVersion?, componentTypeName?, fromFrame?, toFrame?, limit (default 100)
Returns: [{ frame, changeType, entityId, componentType, timestamp }]
```

#### `find_symbol_usages`
Roslyn-based project-wide symbol search. Finds all references to a type, method, field, or property across the project's C# source. Useful for finding every place a component is touched (read, written, added, removed) — supplements the static flow maps.
```
Parameters: symbolName (string), symbolKind ("type"|"method"|"field"|"property"), assemblyFilter? (string)
Returns: [{ file, line, column, usageKind, containingType, snippet }]
```

#### `validate_csharp` (ported from Coplay, improved)
Roslyn validation with the **full project in scope** — not just an isolated snippet. Resolves imports, checks type accessibility across assemblies, catches `using` directives that cannot be resolved.
```
Parameters: filePath (string), strictMode (bool)
Returns: { valid: bool, errors: [{ message, file, line, code }], warnings[] }
```

*Implementation: uses a `Microsoft.CodeAnalysis.Workspace` loaded from the project's solution file or assembly definitions, so all assembly references are present.*

#### `reflect_type` (ported from Coplay)
Live C# type/method introspection via reflection at runtime.
```
Parameters: typeName (fully qualified), includePrivate (bool)
Returns: { typeName, methods[], properties[], fields[], interfaces[], baseType }
```

---

## Layer 2: External Debugger MCP Server

*Deferred to a separate plan. To be built when breakpoint-halted inspection is needed.*

*Design decision recorded: use `Mono.Debugger.Soft` direct TCP client (MIT) — not `UnityDebugAdapter.dll` (proprietary, brittle outside VS Code). Will include `get_journal_at_breakpoint` as a pre-built convenience query alongside `evaluate_expression`.*

---

## Layer 3: Debugging Skills (Slash Commands)

**Integration point**: the debugging workflows below are sub-procedures referenced from the existing `fix-unity-errors` skill (`~/.claude/skills/fix-unity-errors`). That skill is also updated to use the new MCP tools (`run_and_capture_error`, `wait_until_ready`) instead of manual console inspection steps.

**Workflow files location**: `.claude/commands/` (in this utils repo)

### Updated `fix-unity-errors` skill
- Replace manual "check console for errors" step with `run_and_capture_error` tool call
- Replace manual "wait for compilation" with `wait_until_ready`
- After a runtime error is returned: route to the appropriate sub-workflow below based on error type

### Sub-workflow: `diagnose-runtime-error.md`
Entry point after `run_and_capture_error` returns a runtime error. Routes by error category:

- **Missing component exception** → `trace-missing-component`
- **Invalid/missing entity** → `trace-missing-entity`
- **Unresolved entity reference** → check baking output, subscene load state (specific DOTS version mismatch error)
- **Assumption violation / unexpected state** → write a simulation test (setup state → run N frames → assert outcome)

Read the stacktrace first. Identify system, line, and component/entity before calling any tools.

### Sub-workflow: `trace-missing-component.md`
For "component X is missing from entity Y at runtime":
1. **Identify component + accessing context** from stacktrace
2. **Consult the flow map** — which systems write this component?
3. **Check entity's current archetype** via `get_entity_archetype`
4. **Check entity's structural history** via `get_entity_journal`
   - Never added → responsible system's query didn't match → check its required components (recurse if also missing) + check `get_system_execution_order` for ordering
   - Added then removed → find removing system via journal timestamp + flow map
5. **ECB timing** — if added via ECB, verify playback system runs before the accessor (`get_system_execution_order`)
6. **Conditional breakpoint** on responsible system if still unclear

*Transitive: a missing component may depend on another missing component. Follow the chain.*

### Sub-workflow: `trace-missing-entity.md`
For "entity / singleton does not exist when accessed":
1. **`get_entity_journal`** — was it ever created?
   - Never created → baking issue (subscene load, GameObjectWorld reference, baker config)
   - Created then destroyed → find destroying system via journal + flow map; check for incorrect query match
2. **Subscene check** via `get_entity_archetype` on the singleton; absent → confirm subscene loaded
3. **Stale reference** → `InvalidOperationException`/`EntityNotFoundException` with version mismatch — not missing, just stale reference

### Sub-workflow: `inspect-entity.md`
Utility called from other sub-workflows:
1. `get_entity_archetype` — current components
2. `get_entity_journal` — full structural history
3. Cross-reference absences with flow map to identify responsible system

---

## Delivery Order

| Priority | Deliverable | Rationale |
|---|---|---|
| 1 | `wait_until_ready` + `get_editor_state` | Fixes agent-impatience immediately |
| 2 | `run_and_capture_error` | The core loop entry point |
| 3 | `get_ecs_worlds` + `get_system_execution_order` | Execution order visibility |
| 4 | `query_entities` + `get_entity_archetype` | Core missing-component diagnosis |
| 5 | `get_entity_journal` | History tracing |
| 6 | `find_symbol_usages` + `validate_csharp` + `reflect_type` | Roslyn tooling + Coplay replacement |
| 7 | Update `fix-unity-errors` + sub-workflow skill files | Integrates new tools into existing debugging procedure |

---

## File Structure

```
utils/
  ecs-mcp-unity-package/           # Unity UPM package (referenced in game project)
    package.json
    Editor/
      Mordochor.EcsMcp.Editor.asmdef
      Tools/
        WaitUntilReadyTool.cs
        RunAndCaptureErrorTool.cs
        EditorStateTool.cs
        EcsWorldsTool.cs
        SystemExecutionOrderTool.cs
        EntityQueryTool.cs
        EntityArchetypeTool.cs
        EntityJournalTool.cs
        FindSymbolUsagesTool.cs
        ValidateCSharpTool.cs
        ReflectTypeTool.cs
      Tests/
        Mordochor.EcsMcp.Editor.Tests.asmdef
        WaitUntilReadyToolTests.cs
        RunAndCaptureErrorToolTests.cs
        EntityQueryToolTests.cs
        EntityJournalToolTests.cs
        FindSymbolUsagesToolTests.cs
        ValidateCSharpToolTests.cs

  .claude/
    commands/
      grill-me.md                  # existing
      diagnose-runtime-error.md    # new sub-workflow
      trace-missing-component.md   # new sub-workflow
      trace-missing-entity.md      # new sub-workflow
      inspect-entity.md            # new sub-workflow (utility)
    # fix-unity-errors skill updated on user's local machine (~/.claude/skills/)
```

---

## Open TBDs (need game project access to resolve)

1. **Debugger port**: Unity Editor soft debugger default is 56000; verify against project's launch configuration
2. **Journal availability**: `EntityChangeJournal` requires `UNITY_EDITOR` or `ENABLE_UNITY_COLLECTIONS_CHECKS`; confirm enabled in project's debug build config
3. **Flow map format**: `find_symbol_usages` and skills reference the static flow map data — the exact format (Mermaid source files, companion JSON) and file paths are TBD until working in the game project
4. **`validate_csharp` workspace loading**: project may use Assembly Definition files rather than a `.sln`; Roslyn workspace construction strategy depends on this
