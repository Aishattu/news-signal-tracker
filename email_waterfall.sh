#!/bin/bash
# Clay email waterfall: cheapest vendors first (all <= 2 credits), stop at first hit,
# then verify with Enrow (1 credit). Retries the verify once on timeout.
#
# usage:  ./email_waterfall.sh "Full Name" domain.com "Company Name"
# stdout: Full Name|email|found_by|verification      (blank fields = not found)
# stderr: per-vendor log
#
# Costs: Icypeas 0.5 · Enrow/LeadMagic/Kitt 1 · Findymail/Prospeo/Hunter 2 · verify 1
# Package ids come from `clay workflows actions list`; re-check if a vendor call errors.

N="$1"; D="$2"; C="$3"
run(){ clay workflows actions test "$1" "$2" --inputs "$3" 2>&1; }
try(){ # label pkg key inputs jqpath
  out=$(run "$2" "$3" "$4")
  echo "[$1] $(echo "$out" | jq -c '{r:.result, e:.error.message}' 2>/dev/null | cut -c1-300)" >&2
  echo "$out" | jq -r "$5 // empty" 2>/dev/null | grep -E '^[^ @]+@[^ @]+\.[a-z]+$' | head -1
}

chain=(
 "Icypeas|303cd8bc-26dc-4c8c-bd5a-e94528d6c77d|icypeas-find-email-v2|{\"fullname\":\"$N\",\"domain\":\"$D\"}|.result.email"
 "Enrow|c1169e49-b7e3-4908-aac1-61883df5ccc5|enrow-find-work-email|{\"name\":\"$N\",\"domain\":\"$D\",\"company\":\"$C\"}|.result.result.email"
 "LeadMagic|edb58209-a62d-42be-992a-e41b87eeacc2|leadmagic-find-work-email|{\"name\":\"$N\",\"domain\":\"$D\"}|.result.email"
 "Kitt|80eadf57-480e-4f7f-bc4a-79708415de44|kitt-find-work-email|{\"fullName\":\"$N\",\"domain\":\"$D\"}|.result.email"
 "Findymail|9515bb04-4267-4074-94eb-653545c3c38f|findymail-find-work-email|{\"full_name\":\"$N\",\"company_domain\":\"$D\"}|.result.email"
 "Prospeo|48a31bbb-63e6-4461-8a62-d88bb2cd6b0f|prospeo-find-work-email-v2|{\"full_name\":\"$N\",\"company_domain\":\"$D\"}|.result.email"
 "Hunter|9cfc7721-5c91-423b-a0b0-4cc1f42c6089|find-email-v2|{\"full_name\":\"$N\",\"domain\":\"$D\"}|.result.email"
)

E=""; SRC=""
for c in "${chain[@]}"; do
  IFS='|' read -r L P K I J <<<"$c"
  E=$(try "$L" "$P" "$K" "$I" "$J")
  if [ -n "$E" ]; then SRC=$L; break; fi
done

Q=""
if [ -n "$E" ]; then
  for attempt in 1 2; do
    v=$(run c1169e49-b7e3-4908-aac1-61883df5ccc5 enrow-validate-work-email "{\"email\":\"$E\"}")
    echo "[Enrow verify #$attempt] $(echo "$v" | jq -c '{r:.result,e:.error.message}' | cut -c1-200)" >&2
    Q=$(echo "$v" | jq -r '.result.qualification // empty')
    [ -n "$Q" ] && break
  done
fi
echo "$N|$E|$SRC|$Q"
