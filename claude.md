## Development Guidelines

- Keep code comments to a minimum with minimal verbosity.
- Restrict file access to only those files or directories explicitly referenced in the prompt. Do not inspect, modify, or create files outside the requested scope unless explicitly instructed.
- Never create, amend, or push commits unless the user explicitly requests it.

## Code Quality & Architecture

- Consistently apply clean code principles throughout the codebase:
  - Prioritize readability, simplicity, and maintainability over clever implementations.
  - Keep functions, classes, and modules focused on a single responsibility.
  - Use descriptive, consistent naming and clear abstractions.
  - Eliminate duplication where practical without over-engineering.
  - Avoid hardcoded values; use configuration, constants, or dependency injection where appropriate.
  - Remove dead code, unused imports, obsolete logic, and unnecessary complexity.
  - Write code that is modular, testable, and easy to extend.

- Always preserve and respect the existing architecture:
  - Follow the established microservice boundaries and responsibilities.
  - Never move business logic between services unless explicitly requested.
  - Preserve API contracts and service interfaces unless the task requires changing them.
  - Keep services loosely coupled and avoid introducing hidden dependencies.
  - Place new code in the appropriate layer (API, service, domain, data access, worker, etc.) rather than bypassing the project's structure.

## Security

- Never expose, log, hardcode, or commit secrets, credentials, API keys, tokens, passwords, or other sensitive information.
- Use environment variables or the project's existing secret management mechanism for sensitive configuration.
- Follow secure-by-default practices and avoid introducing unnecessary security risks.