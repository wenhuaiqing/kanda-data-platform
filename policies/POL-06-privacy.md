# POL-06 Privacy and personal information in data

Synthetic policy written for this demonstration.

## 1. Where personal information lives
Clients' and workers' names, dates of birth, phone numbers, addresses and NDIS numbers stay in the source systems and the restricted landing zone. Governed tables, reports, ad hoc queries and any model use ids instead.

## 2. Free text
Free text - visit notes, comments - may contain anything. It is scanned and masked before it leaves the landing zone: phone numbers, NDIS numbers and the names of clients on the client master. Masking is a floor; what it misses is reviewed and the rules improved.

## 3. Access by role
Access to governed data is by role and enforced in the data, not in the report: a coordinator sees their region's clients and services, Finance sees claims without visit notes, executives see aggregates. A new role is a reviewed change.

## 4. Models
A language model receives only what the role it runs as can see, and only for the record it is working on. It never receives a personal identifier. Its output is a proposal, recorded with what it was shown.
