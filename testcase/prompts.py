
child_prompt = """
You are analyzing a standalone Haskell function to extract metadata for automated test generation and program analysis.

This function **does not call any other functions** within our codebase — it is considered a *leaf node*.

---
## Your Task:

Analyze the function code and extract the following metadata:

1. **function_name**: Full module-qualified name (if provided; else use placeholder)
2. **behavior_summary**: A concise, 1–2 sentence description of what this function does.
3. **preconditions**:
   - Conditions that must be true before this function is executed.
   - These could include:
     - Required DB records or constraints
     - Required values in the input
     - Required environment variables or config values
     - Anything that *must* exist or be true for the function to work as expected
4. **postconditions**:
   - What changes as a result of this function executing
   - Could include:
     - DB records created/updated
     - Files written, logs created, external calls made
     - Return values or mutations
5. **state_dependencies**: 
   - Does this function access any state like:
     - Database tables? Which ones? For reading or writing?
     - Environment variables? Which ones?
     - Redis keys or queues?
6. **side_effects**:
   - Any effects on external systems
   - e.g., DB inserts, external API calls, writing to file system, sending emails

---

## Function Code:

```haskell
{code}
```
### Output Format:
Return only a **valid JSON object** like this:

{{
  "function_name": "createUserHandler",
  "behavior_summary": "Handles user creation by inserting a new user into the DB and writing an audit log.",
  "preconditions": [
    "No existing user with the same email in users table",
    "Valid CreateUserRequest received in the HTTP body"
  ],
  "postconditions": [
    "New user is inserted into users table",
    "Audit log is written"
  ],
  "state_dependencies": {{
    "db": ["user key must be present"],
    "env": ["EMAIL_VALIDATION_ENABLED"]
  }},
  "side_effects": [
    "DB insert into users table",
    "Write to audit log"
  ]
}}
"""

parent_prompt = """
You are analyzing a Haskell function that calls one or more other functions.

Your goal is to produce an accurate, structured metadata summary for this function, suitable for automated QA, test generation, and documentation.

---

## Your Input:

1. **The function code**
2. **Metadata for the functions it directly calls** (immediate children)

These child functions may handle business logic, database access, or external effects. Their metadata has been extracted and is provided to help you reason more accurately about what this parent function does.

---

## Your Tasks:

Analyze both the **function code** and the **metadata of its child functions** to produce these fields:

1. **function_name**: The full qualified function name (if known; else placeholder)
2. **behavior_summary**: A concise 1–2 sentence summary describing:
   - What this function does
   - How it composes or delegates logic to child functions
3. **preconditions**:
   - What must be true for this function to execute successfully?
   - Include:
     - Input expectations
     - Required DB rows or schema state
     - Environment variables or configurations
     - Any assumptions carried up from child functions (merge or restate clearly)
4. **postconditions**:
   - What outcomes or changes result from this function?
   - Include:
     - Final return effects (return values, computed structures)
     - DB records created/updated
     - Combined or filtered results from child functions
5. **state_dependencies**:
   - DB tables, environment variables, Redis keys this function depends on
   - Include both **its own access** and that of child functions (merged)
6. **side_effects**:
   - External writes or observable behavior
   - DB inserts, logging, API calls, file operations, etc.
   - Include any side effects from called children

---

## Input Code:

```haskell
{code}
```

## Child Metadata:

{metadata}

### Output Format:
Return only a **valid JSON object** like this:

{{
  "function_name": "createUserHandler",
  "behavior_summary": "Handles user creation by inserting a new user into the DB and writing an audit log.",
  "preconditions": [
    "No existing user with the same email in users table",
    "Valid CreateUserRequest received in the HTTP body"
  ],
  "postconditions": [
    "New user is inserted into users table",
    "Audit log is written"
  ],
  "state_dependencies": {{
    "db": ["user key must be present"],
    "env": ["EMAIL_VALIDATION_ENABLED"]
  }},
  "side_effects": [
    "DB insert into users table",
    "Write to audit log"
  ]
}}
"""


parent_promptv2 = """
You are analyzing a Haskell function that invokes one or more child functions.

Your goal is to generate a structured and accurate metadata summary for this function. This metadata will be used for:

- Automated test generation
- QA scenario design
- API documentation and reasoning about system behavior
---

## You Are Given:

1. The **source code** of this parent function
2. The **metadata for its immediate child functions**, which it may call directly

These child functions may contain database logic, API calls, conditional branching, or other side effects. Use their metadata to better understand how the parent function composes or orchestrates them.
---

## Your Tasks:

Based on the **parent function code** and **child function metadata**, return a **valid JSON object** describing the parent function with these fields:

1. **function_name**: The full qualified function name (if known; else placeholder)
2. **behavior_summary**: A concise 1–2 sentence summary describing:
   - What this function does
   - How it composes or delegates logic to child functions
3. **preconditions**:
   - What must be true for this function to execute successfully?
   - Include:
     - Input expectations
     - Required DB rows or schema state
     - Environment variables or configurations
     - Any assumptions carried up from child functions (merge or restate clearly)
4. **postconditions**:
   - What outcomes or changes result from this function?
   - Include:
     - Final return effects (return values, computed structures)
     - DB records created/updated
     - Combined or filtered results from child functions
5. **state_dependencies**:
   - DB tables, environment variables, Redis keys this function depends on
   - Include both **its own access** and that of child functions (merged)
6. **side_effects**:
   - External writes or observable behavior
   - DB inserts, logging, API calls, file operations, etc.
   - Include any side effects from called children
7. **child_call_relationship**:
   - For each child, specify how and when it's called:
   - "always" → called unconditionally
   - "if condition" → conditionally called (state/input based)
   - "only if X" → only under special input/data/env conditions
   - "inside case on gateway" → explain branching logic
---

## Input Code:

```haskell
{code}
```

## Child Metadata:

{metadata}

### Output Format:
Return only a **valid JSON object** like this:

{{
  "function_name": "createUserHandler",
  "behavior_summary": "Handles user creation by inserting a new user into the DB and writing an audit log.",
  "preconditions": [
    "No existing user with the same email in users table",
    "Valid CreateUserRequest received in the HTTP body"
  ],
  "postconditions": [
    "New user is inserted into users table",
    "Audit log is written"
  ],
  "state_dependencies": {{
    "db": ["user key must be present"],
    "env": ["EMAIL_VALIDATION_ENABLED"]
  }},
  "side_effects": [
    "DB insert into users table",
    "Write to audit log"
  ],
  "child_call_relationship": [
    {{ child: child function name,condition: what condition parent fun call this fun }}
  ]
}}

Notes:

Keep the response strictly structured and factual.
Do not hallucinate child function names — take them from the provided metadata.
Focus especially on when and why a child function is called, based on parent logic.
Feel free to reword, clarify, or merge preconditions/postconditions from children where helpful
"""