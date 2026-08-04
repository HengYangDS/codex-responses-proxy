## 1. One owner for the route contract

- [x] 1.1 Remove the duplicated route-resolution sentence from the Responses
  admission requirement, leaving it to state fail-closed projection only.
- [x] 1.2 Move the ambiguous-suffix scenario to the route requirement and
  replace its stale "non-Responses endpoint" wording, which the admitted
  `GET /<provider>/v1/models` target had made false.
- [x] 1.3 Carry "lexically normalized" onto the route requirement so the dedupe
  drops no meaning.

## 2. Connection framing on a refused request

- [x] 2.1 Add a RED wire contract sending a rejected request with a body
  followed by a second request on one connection; observe two responses where
  one is expected, the second synthesized from the unread body.
- [x] 2.2 Add the same RED for the drain toggle, which answers without reading a
  body at all.
- [x] 2.3 Declare `Connection: close` on both rejections and on the drain
  toggle; obtain focused GREEN.
- [x] 2.4 Guard the converse — a locally answered request whose body was read
  stays reusable — and prove the guard is not vacuous by mutation.

## 3. Verification

- [x] 3.1 Run full quality with statement and branch coverage above 95 percent.
- [x] 3.2 Confirm no remaining response path answers before its body is
  consumed without declaring the connection closed.

## 4. Post-archive acceptance boundary

The following are live-system claims. They remain open after this repository
change is archived and must not be marked complete by OpenSpec archival.

- A reinstall must place the fixed listener under supervision before any live
  client observes the repaired framing.
- `aigw check` must still report the same route diagnosis, since it probes
  rejected paths and now receives a closed connection with each 404.
