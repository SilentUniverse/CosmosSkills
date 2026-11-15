---- MODULE Checkout ----
EXTENDS Naturals
VARIABLES phase, charges
vars == <<phase, charges>>

Init == phase = "cart" /\ charges = 0
YouPay == phase = "cart" /\ phase' = "paying" /\ UNCHANGED charges
BankCharges == phase = "paying" /\ phase' = "charged" /\ charges' = charges + 1
ReplyLost == phase = "charged" /\ phase' = "failed" /\ UNCHANGED charges
Timeout == phase = "paying" /\ phase' = "failed" /\ UNCHANGED charges
Retry == phase = "failed" /\ phase' = "paying" /\ UNCHANGED charges
Confirm == phase = "charged" /\ phase' = "paid" /\ UNCHANGED charges
Done == phase = "paid" /\ UNCHANGED vars

Next == YouPay \/ BankCharges \/ ReplyLost \/ Timeout \/ Retry \/ Confirm \/ Done

AtMostOneCharge == charges <= 1
Small == charges <= 2
====
