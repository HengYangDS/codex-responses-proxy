# Design

The fixture must not assume the clone's initial branch name. `git checkout -B`
establishes the required fixture branch whether it already exists or not.

OpenSSH private keys are opaque serialized bytes. Encoding the already loaded
UTF-8 payload and writing bytes avoids platform newline translation without a
second implementation path.
