---- MODULE TaskFlow ----
EXTENDS Naturals
VARIABLES phase, mode, submit, hasChecks, intentConfirmed, started, coded, verified, ci, fails
vars == <<phase, mode, submit, hasChecks, intentConfirmed, started, coded, verified, ci, fails>>

Init ==
  /\ phase = "request"
  /\ mode \in {"plan", "direct"}
  /\ submit \in BOOLEAN
  /\ hasChecks \in BOOLEAN
  /\ intentConfirmed = FALSE
  /\ started = FALSE /\ coded = FALSE /\ verified = FALSE /\ ci = FALSE /\ fails = 0

Same == UNCHANGED <<mode, submit, hasChecks>>

RestateForPlan == phase = "request" /\ mode = "plan"
  /\ phase' = "confirming_intent"
  /\ Same /\ UNCHANGED <<intentConfirmed, started, coded, verified, ci, fails>>

ReviseIntent == phase = "confirming_intent" /\ UNCHANGED vars

ConfirmIntent == phase = "confirming_intent"
  /\ phase' = "aligning" /\ intentConfirmed' = TRUE
  /\ Same /\ UNCHANGED <<started, coded, verified, ci, fails>>

PlanDecision == phase = "aligning" /\ UNCHANGED vars

GivePlan == phase = "aligning" /\ intentConfirmed
  /\ phase' = "planned"
  /\ Same /\ UNCHANGED <<intentConfirmed, started, coded, verified, ci, fails>>

UserSaysOk == phase = "planned" /\ UNCHANGED vars

UserRevisesPlan == phase = "planned"
  /\ phase' = "aligning"
  /\ Same /\ UNCHANGED <<intentConfirmed, started, coded, verified, ci, fails>>

UserSaysStart == phase = "planned"
  /\ phase' = "coding" /\ started' = TRUE
  /\ Same /\ UNCHANGED <<intentConfirmed, coded, verified, ci, fails>>

StartDirect == phase = "request" /\ mode = "direct"
  /\ phase' = "coding" /\ started' = TRUE
  /\ Same /\ UNCHANGED <<intentConfirmed, coded, verified, ci, fails>>

NeedDecision == phase = "coding" /\ phase' = "asking"
  /\ Same /\ UNCHANGED <<intentConfirmed, started, coded, verified, ci, fails>>

UserDecides == phase = "asking" /\ phase' = "coding"
  /\ Same /\ UNCHANGED <<intentConfirmed, started, coded, verified, ci, fails>>

ReadyCheck == phase = "coding" /\ phase' = "verifying" /\ coded' = TRUE /\ verified' = FALSE /\ ci' = FALSE
  /\ Same /\ UNCHANGED <<intentConfirmed, started, fails>>

VerifyPass == phase = "verifying" /\ phase' = "verified" /\ verified' = TRUE
  /\ Same /\ UNCHANGED <<intentConfirmed, started, coded, ci, fails>>

Fail(from) == phase = from
  /\ (IF fails < 1 THEN phase' = "coding" /\ fails' = fails + 1 ELSE phase' = "blocked" /\ fails' = fails)
  /\ Same /\ UNCHANGED <<intentConfirmed, started, coded, verified, ci>>

VerifyFail == Fail("verifying")

Rethink == phase = "blocked" /\ phase' = "coding" /\ fails' = 0
  /\ Same /\ UNCHANGED <<intentConfirmed, started, coded, verified, ci>>

StopLocal == phase = "verified" /\ ~submit /\ phase' = "stopped"
  /\ Same /\ UNCHANGED <<intentConfirmed, started, coded, verified, ci, fails>>

Land == phase = "verified" /\ submit /\ hasChecks /\ phase' = "landing"
  /\ Same /\ UNCHANGED <<intentConfirmed, started, coded, verified, ci, fails>>

LandNoChecks == phase = "verified" /\ submit /\ ~hasChecks /\ phase' = "merged"
  /\ Same /\ UNCHANGED <<intentConfirmed, started, coded, verified, ci, fails>>

CiPass == phase = "landing" /\ phase' = "merged" /\ ci' = TRUE
  /\ Same /\ UNCHANGED <<intentConfirmed, started, coded, verified, fails>>

CiFail == Fail("landing")

Done == phase \in {"stopped", "merged"} /\ UNCHANGED vars

Next == RestateForPlan \/ ReviseIntent \/ ConfirmIntent \/ PlanDecision \/ GivePlan
  \/ UserSaysOk \/ UserRevisesPlan \/ UserSaysStart \/ StartDirect
  \/ NeedDecision \/ UserDecides \/ ReadyCheck \/ VerifyPass \/ VerifyFail
  \/ Rethink \/ StopLocal \/ Land \/ LandNoChecks \/ CiPass \/ CiFail \/ Done

NoPlanBeforeIntentConfirmed == (mode = "plan" /\ phase \in {"aligning", "planned"}) => intentConfirmed
NoCodeDuringPlan == (mode = "plan" /\ phase \in {"request", "confirming_intent", "aligning", "planned"}) => ~started /\ ~coded
NoCodeBeforeStart == coded => started
MergeNeedsProofAndCi == phase = "merged" => verified /\ (hasChecks => ci)
LandOnlyWhenAsked == phase \in {"landing", "merged"} => submit
DoneOnlyWhenVerified == phase \in {"stopped", "merged"} => verified
====
