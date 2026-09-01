# Security Policy

## Supported versions

Security fixes are applied to the latest release on the `main` branch.

## Reporting a vulnerability

Please do not publish exploitable details in a public issue. Use GitHub's
private vulnerability reporting feature for the repository when it is
available, and include reproduction steps, affected versions, and impact.

## Trust boundary

Confuser Obfuser transforms source code without executing it by default.
The optional behavior validator executes both the original and transformed
programs. Only enable validation for code you trust. Validation is not a
sandbox and does not prevent file, network, process, or other side effects.
