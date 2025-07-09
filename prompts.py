


user_prompt = """
You are a static analyzer for Haskell backend code. Given a function, extract precise and structured metadata that will help QA engineers test the API that executes this function. Focus only on test-relevant behavior and internal state expectations.

Return a valid JSON object with the following fields:

- function_name: Name of the top-level function.
- behavior_summary: One-line summary of the function’s purpose and what it does.
- preconditions: What must already exist or be true for the function to work correctly. Include things like:
  - Required DB entries (e.g., "user with id must exist in users table")
  - Redis/cache keys
  - Required config/env flags
- postconditions: What this function guarantees after successful execution — e.g., DB changes, logs written, events emitted.
- state_dependencies: All external state the function reads or checks, such as:
  - DB tables and filters (e.g., "reads discounts where code = ?")
  - Redis keys (e.g., "cart:<user_id>:value")
  - Env/config (e.g., "DISCOUNT_FEATURE_ENABLED")
- side_effects: What this function changes in the system — inserts, updates, logs, metrics, etc.

### Code (Haskell):
{code}

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

summarize_prompt = """
You are assisting with automated test generation for a Haskell backend API.

We are currently analyzing the function `{current_function}` in the call path to a recently modified function.

Here is what you need to know:

- This function may call many **descendant functions**, **excluding `{next_function}`**, which will be analyzed separately.
- The goal is to understand **what is required (DB, state, environment, config)** for this function and its local children to work correctly.
- You will receive metadata for all these descendant functions (except the main path forward).
- Your job is to **summarize the test setup needs** implied by these descendant functions.

---

## Function currently being analyzed:
{current_function}

## These are its descendant functions (excluding the next main-path function `{next_function}`):

{metainfo}  
# (This is a newline-separated collection of behavior summaries, preconditions, state dependencies, etc.)
---

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