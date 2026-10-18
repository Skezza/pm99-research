# 2015/16 English 92 player-rating fallbacks

These forty players did not have a sufficiently reliable individual FIFA
attribute source in the 2015/16 compiler. They use the declared
position-and-tier fallback in `player-ledger.json`, rather than silently
pretending to be individually sourced.

The shared attributes are ordered as `speed, stamina, aggression, passing,
dribbling, tackling, heading, shooting`. Heading is adjusted for each player's
height. Quality is shown per player.

| Role | Shared fallback attributes |
| --- | --- |
| Goalkeeper | 48, 58, 48, 52, 32, 45, 42, 20 |
| Defender | 62, 70, 70, 62, 57, 70, height-adjusted, 46 |
| Midfielder | 66, 72, 62, 70, 68, 62, height-adjusted, 60 |
| Forward | 69, 67, 62, 61, 70, 42, height-adjusted, 73 |

| Club | Player | Role | Quality |
| --- | --- | --- | ---: |
| Aston Villa | Bradley Watkins | G | 72 |
| Barnet | Elliott Johnson | D | 54 |
| Barnet | Kai McKenzie Lyle | G | 52 |
| Barnet | Matty Stevens | F | 52 |
| Barnet | Mauro Vilhete | M | 54 |
| Barnet | Sam Muggleton | D | 52 |
| Barnsley | Mike Phenix | F | 58 |
| Blackpool | Jose Miguel Cubero | M | 58 |
| Bradford City | Joe Cracknell | G | 58 |
| Brentford | Mark Smith | G | 64 |
| Cambridge United | Jordan Chiedozie | F | 52 |
| Carlisle United | Kevin Osei | M | 52 |
| Dagenham & Redbridge | Lewis Moore | G | 52 |
| Dagenham & Redbridge | Matt Partridge | D | 52 |
| Dagenham & Redbridge | Nyron Nosworthy | D | 54 |
| Fleetwood Town | Declan McManus | F | 58 |
| Fleetwood Town | Lyle Della-Verde | M | 60 |
| Hartlepool United | Peter Denton | G | 52 |
| Leyton Orient | Frazer Shaw | D | 54 |
| Leyton Orient | Freddy Moncur | M | 52 |
| Newport County | Aaron Hayden | D | 52 |
| Newport County | Joe Green | G | 52 |
| Nottingham Forest | Ross Durrant | G | 64 |
| Notts County | Civard Sprockel | D | 52 |
| Notts County | Gill Swerts | D | 52 |
| Notts County | Julian Jenner | F | 52 |
| Portsmouth | Matt Tubbs | F | 54 |
| Rochdale | Johny Diba | G | 58 |
| Rotherham United | Aidy White | D | 64 |
| Scunthorpe United | Ben Ledger | G | 58 |
| Stevenage | Ben Jackson | G | 52 |
| Stevenage | Brett Williams | F | 54 |
| Stevenage | Dipo Akinyemi | M | 52 |
| Wigan Athletic | Ryan Jennings | M | 58 |
| Yeovil Town | Iffy Allen | F | 52 |
| Yeovil Town | James Needle | G | 52 |
| Yeovil Town | Jamie Burrows | F | 52 |
| York City | Anthony Straker | D | 52 |
| York City | Marvin McCoy | D | 54 |
| York City | Reece Thompson | F | 52 |
