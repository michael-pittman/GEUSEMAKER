Optional: drop prebuilt amazon-efs-utils packages here to avoid downloading/building on the instance.

- Debian/Ubuntu: place `.deb` files (e.g., `amazon-efs-utils_*.deb`)
- Amazon Linux: place `.rpm` files (e.g., `amazon-efs-utils-*.rpm`)

When present, UserData will install from these packages before falling back to OS package managers.
