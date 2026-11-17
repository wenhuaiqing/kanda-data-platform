# POL-03 Rostering, time bands and the support catalogue

Synthetic policy written for this demonstration. The catalogue codes and prices in this demonstration are invented.

## 1. Choosing the item
Each service is claimed against one item in the support catalogue. The item has a funding type (NDIS or Support at Home), a support, and a time band.

## 2. Time bands
The time band is the band of the shift's start time: weekday daytime 06:00 to 19:59, weekday evening 20:00 to 23:59, Saturday, and Sunday. A Saturday shift on the weekday item is on the wrong item; it is repriced to the Saturday item before it is claimed.

## 3. Price limits
A service is claimed at no more than the price limit of its item on the date of service. A client rate in the roster above the limit is repriced to the limit, and the roster rate is corrected so the next service is right.
