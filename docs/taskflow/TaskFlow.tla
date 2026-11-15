---- MODULE TaskFlow ----
EXTENDS Naturals
VARIABLES phase, mode, submit, started, coded, verified, ci, fails
vars == <<phase, mode, submit, started, coded, verified, ci, fails>>

Init ==
  /\ phase = "request"
  /\ mode \in {"plan", "direct"}
  /\ submit \in BOOLEAN
  /\ started = FALSE /\ coded = FALSE /\ verified = FALSE /\ ci = FALSE /\ fails = 0

Same == UNCHANGED <<mode, submit>>

GivePlan == phase = "request" /\ mode = "plan" /\ phase' = "planned"
  /\ Same /\ UNCHANGED <<started, coded, verified, ci, fails>>
StartDirect == phase = "request" /\ mode = "direct" /\ phase' = "coding" /\ started' = TRUE
  /\ Same /\ UNCHANGED <<coded, verified, ci, fails>>
UserSaysOk == phase = "planned" /\ UNCHANGED vars
UserSaysStart == phase = "planned" /\ phase' = "coding" /\ started' = TRUE
  /\ Same /\ UNCHANGED <<coded, verified, ci, fails>>
NeedDecision == phase = "coding" /\ phase' = "asking"
  /\ Same /\ UNCHANGED <<started, coded, verified, ci, fails>>
UserDecides == phase = "asking" /\ phase' = "coding"
  /\ Same /\ UNCHANGED <<started, coded, verified, ci, fails>>
Commit == phase = "coding" /\ phase' = "committed" /\ coded' = TRUE /\ verified' = FALSE /\ ci' = FALSE
  /\ Same /\ UNCHANGED <<started, fails>>
Dispatch == phase = "committed" /\ phase' = "verifying"
  /\ Same /\ UNCHANGED <<started, coded, verified, ci, fails>>
VerifyPass == phase = "verifying" /\ phase' = "verified" /\ verified' = TRUE
  /\ Same /\ UNCHANGED <<started, coded, ci, fails>>
Fail(from) == phase = from
  /\ (IF fails < 1 THEN phase' = "coding" /\ fails' = fails + 1 ELSE phase' = "blocked" /\ fails' = fails)
  /\ Same /\ UNCHANGED <<started, coded, verified, ci>>
VerifyFail == Fail("verifying")
Rethink == phase = "blocked" /\ phase' = "coding" /\ fails' = 0
  /\ Same /\ UNCHANGED <<started, coded, verified, ci>>
StopLocal == phase = "verified" /\ ~submit /\ phase' = "stopped"
  /\ Same /\ UNCHANGED <<started, coded, verified, ci, fails>>
Land == phase = "verified" /\ submit /\ phase' = "landing"
  /\ Same /\ UNCHANGED <<started, coded, verified, ci, fails>>
CiPass == phase = "landing" /\ phase' = "merged" /\ ci' = TRUE
  /\ Same /\ UNCHANGED <<started, coded, verified, fails>>
CiFail == Fail("landing")
Done == phase \in {"stopped", "merged"} /\ UNCHANGED vars

Next == GivePlan \/ StartDirect \/ UserSaysOk \/ UserSaysStart \/ NeedDecision \/ UserDecides
  \/ Commit \/ Dispatch \/ VerifyPass \/ VerifyFail \/ Rethink \/ StopLocal \/ Land
  \/ CiPass \/ CiFail \/ Done

NoCodeBeforeStart == coded => started
MergeNeedsProofAndCi == phase = "merged" => verified /\ ci
LandOnlyWhenAsked == phase \in {"landing", "merged"} => submit
DoneOnlyWhenVerified == phase \in {"stopped", "merged"} => verified
====
