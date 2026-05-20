# 05 — Frontend ↔ Backend integration matrix

Legend: OK = endpoint exists + client wired + (where noted) runtime-tested · PARTIAL = wired but feature blocked/incomplete · NOT WIRED = backend exists, no UI caller · NOT VERIFIED = not exercised at runtime.

| Frontend page/component | UI action | API method/path | Backend exists? | Schema match | Runtime tested | Status | Evidence |
|---|---|---|---|---|---|---|---|
| characters/page | list | GET /api/v1/characters | yes | yes | yes (200, 5 chars) | OK | psql + UI 200 |
| characters/new | create | POST /api/v1/characters | yes | yes | yes (create works in tests) | OK | 926 tests |
| characters/new + [id] | voice picker | GET /api/v1/characters/available-voices | yes | list[str] | yes (returns 3 free voices) | OK | curl |
| characters/[id] | activate/edit/retire | POST /api/v1/characters/{id}/status | yes | yes | yes (live smoke earlier) | OK | session smoke |
| characters/[id] | clone profile | POST /api/v1/characters/{id}/clone | yes | yes | yes (live clone+delete) | OK | session smoke |
| CharacterImageLibrary | Generate initial face | POST …/images/generate-initial | yes | yes | **yes — real 1MB 768×1024 PNG** | OK | id 51e38630, PNG magic 89504e47 |
| CharacterImageLibrary | Generate variation | POST …/images/generate-consistent | yes | yes | yes → **422 (no full-body ref)** | PARTIAL | all chars has_body=f |
| CharacterImageLibrary | set main reference | POST …/{img}/set-main-reference | yes | yes | yes (tests) | OK | tests |
| CharacterImageLibrary | set full-body reference | POST …/{img}/set-full-body-reference | yes | yes | yes (tests) | OK | test_phase_ig5 |
| CharacterImageLibrary | accept/reject/archive/delete | POST …/{img}/{action} | yes | yes | yes (tests) | OK | tests |
| — (no UI) | upload reference | POST …/images/upload-reference | yes | multipart | endpoint tested; **no UI caller** | NOT WIRED | rg: only lib def |
| — (no UI) | moderate upload | POST …/images/{img}/moderate | yes | form | endpoint tested; **no UI caller** | NOT WIRED | rg: only lib def |
| CreateJobForm | LLM picker default | GET /api/v1/providers/llm | yes | yes | yes (qwen3.6 first) | OK | curl |
| CreateJobForm | TTS picker | GET /api/v1/providers/tts | yes | yes | yes | OK | openapi |
| CreateJobForm | generate script | POST /api/v1/script/generate | yes | yes | not re-tested this audit | NOT VERIFIED | endpoint live |
| CreateJobForm | submit video | POST /api/v1/jobs(/from-inputs) | yes | yes | **pipeline stopped** → won't process | PARTIAL | orchestrator down |
| jobs/page | list videos | GET /api/v1/jobs | yes | yes | yes (empty list) | OK | count=0 |
| jobs/[jobId] | progress/timeline/qc/artifacts | GET …/jobs/{id}/* | yes | yes | n/a (no jobs) | NOT VERIFIED | jobs deleted |
| uploads/page | upload audio/image/text | POST /api/v1/uploads/* | yes | multipart | not re-tested | NOT VERIFIED | endpoints live |
| settings/page | UI settings | GET/PATCH /api/v1/settings/ui | yes | yes | not re-tested | NOT VERIFIED | endpoints live |
| technical-help | tech doc | GET /api/v1/system/technical-architecture[.md] | yes | yes | not re-tested | NOT VERIFIED | endpoints live |

## Key integration findings
1. **upload-reference / moderate** = backend live + lib client present + **zero UI** → unreachable feature (HIGH).
2. **generate-consistent** wired but 422 for all characters (no canonical full-body) → headline feature not demoable (CRITICAL/HIGH).
3. **generate-initial** is the one identity-pipeline path proven end-to-end with a real render (OK).
4. Video submit path is wired but the **DAG workers are stopped** → jobs would sit unprocessed (PARTIAL).
