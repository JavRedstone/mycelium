# checks/mongo/

MongoDB Atlas connectivity check.

Run from the project root (`mycelium/mycelium/`):

```
python checks/mongo/check_mongo.py
```

---

## What it checks

1. Connects to the MongoDB URI in `.env` using Motor (async driver)
2. Pings the server to confirm the connection is live
3. Checks that the configured database (`MONGODB_DB`, default `mycelium`)
   is reachable
4. Lists the collections currently in the database

Nothing is written; no data is modified.

---

## Prerequisites

```
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/
MONGODB_DB=mycelium   # optional, defaults to "mycelium"
```

The URI must be a valid MongoDB connection string (Atlas `+srv` or direct).
Application-layer authentication (e.g. Atlas Data API) is **not** used -
Mycelium uses Motor (Motor wraps PyMongo) for direct driver access.
