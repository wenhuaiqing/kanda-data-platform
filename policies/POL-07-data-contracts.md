# POL-07 Data contracts and change control

Synthetic policy written for this demonstration.

## 1. Every feed has a contract
Each source feed has a data contract: its owner, schedule, freshness, fields, types, classification and rules. A row that breaks the contract is quarantined with the rule it broke. It is never dropped and never fixed in place.

## 2. When a source changes shape
When a vendor or a source system changes what it sends, the contract does not bend to accept it. The quarantine shows the change; the data platform team proposes a new contract version with the mapping, the evidence and a preview of what reprocessing would change; someone other than the proposer approves it; the data reprocesses from the landing zone.

## 3. Vendor releases
Vendors are asked to give notice of interface changes. A release that changes the interface without notice is raised with the vendor through the vendor management process, separately from fixing the data.
