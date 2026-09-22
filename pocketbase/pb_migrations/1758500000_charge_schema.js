/// <reference path="../pb_data/types.d.ts" />

// Charge's storage. PocketBase owns accounts (email/password, Google, Apple) and
// holds each person's data; the Charge API reads and writes it with a superuser
// account. People may READ their own rows (owner = @request.auth.id) but never
// write them directly: every write goes through the API, which validates it.
//
// Every per-person collection cascades on account deletion, except `consents`,
// which must outlive the data it authorised (the API unlinks it on erasure).
migrate((app) => {
  const users = app.findCollectionByNameOrId("users");

  // What the person told us, as plain fields on their account.
  users.fields.add(new NumberField({ name: "birth_year", onlyInt: true, min: 1900, max: 2100 }));
  users.fields.add(new TextField({ name: "sex", max: 20 }));
  users.fields.add(new TextField({ name: "menopause_status", max: 20 }));
  users.fields.add(new TextField({ name: "timezone", max: 64 }));
  users.fields.add(new JSONField({ name: "habits", maxSize: 2000 }));
  users.fields.add(new JSONField({ name: "kit", maxSize: 10000 }));
  // { day_start, day_end, busy: [{ days: [0..6], from, to, label }] } -> the free/busy calendar.
  users.fields.add(new JSONField({ name: "routine", maxSize: 5000 }));
  // Profile fields are written by the API only; people can still change name/avatar/password.
  users.updateRule = "id = @request.auth.id && @request.body.birth_year:isset = false && @request.body.kit:isset = false && @request.body.habits:isset = false && @request.body.routine:isset = false";
  app.save(users);

  const owned = (name, fields, indexes) => {
    const c = new Collection({
      name,
      type: "base",
      listRule: "user = @request.auth.id",
      viewRule: "user = @request.auth.id",
      createRule: null,
      updateRule: null,
      deleteRule: null,
      fields: [
        { name: "user", type: "relation", required: true, collectionId: users.id, cascadeDelete: true, maxSelect: 1 },
        ...fields,
        { name: "created", type: "autodate", onCreate: true, onUpdate: false },
        { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
      ],
      indexes,
    });
    app.save(c);
  };

  // One workout, from any source. `ext_id` dedupes re-uploads and repeat Shortcut runs.
  owned("workouts", [
    { name: "ext_id", type: "text", required: true, max: 120 },
    { name: "source", type: "select", required: true, maxSelect: 1, values: ["export", "shortcut", "manual"] },
    { name: "type", type: "text", required: true, max: 80 },
    { name: "start", type: "text", required: true, max: 19 }, // local wall-clock ISO, no zone
    { name: "duration_min", type: "number", required: true, min: 0, max: 1440 },
    { name: "mean_hr", type: "number", min: 0, max: 260 },
    { name: "effort", type: "text", max: 10 },
    { name: "counts", type: "json", maxSize: 500 },
    { name: "note", type: "text", max: 80 },
  ], [
    "CREATE UNIQUE INDEX idx_workouts_user_ext ON workouts (user, ext_id)",
    "CREATE INDEX idx_workouts_user_start ON workouts (user, start)",
  ]);

  // Per-day summaries from the Health export (sleep feeds the evening sleep rule).
  owned("daily", [
    { name: "date", type: "text", required: true, max: 10 },
    { name: "steps", type: "number" },
    { name: "sleep_hours", type: "number" },
    { name: "sleep_onset", type: "text", max: 5 },
    { name: "exercise_min", type: "number" },
  ], ["CREATE UNIQUE INDEX idx_daily_user_date ON daily (user, date)"]);

  // "More / less like this" votes.
  owned("votes", [
    { name: "activity_id", type: "text", required: true, max: 80 },
    { name: "vote", type: "select", required: true, maxSelect: 1, values: ["more", "less"] },
  ], ["CREATE UNIQUE INDEX idx_votes_user_activity ON votes (user, activity_id)"]);

  // One row per person per day: what we showed (for variety tomorrow) and what they skipped.
  owned("day_log", [
    { name: "date", type: "text", required: true, max: 10 },
    { name: "shown", type: "json", maxSize: 2000 },
    { name: "skips", type: "json", maxSize: 5000 },
  ], ["CREATE UNIQUE INDEX idx_daylog_user_date ON day_log (user, date)"]);

  // Personal tokens for the iOS Shortcut. Only a SHA-256 of the token is stored.
  owned("sync_tokens", [
    { name: "token_hash", type: "text", required: true, max: 64 },
    { name: "last_used", type: "text", max: 30 },
  ], ["CREATE UNIQUE INDEX idx_sync_token_hash ON sync_tokens (token_hash)"]);

  // What they were told and agreed to. Survives account deletion as unlinked evidence.
  const consents = new Collection({
    name: "consents",
    type: "base",
    listRule: "user = @request.auth.id",
    viewRule: "user = @request.auth.id",
    createRule: null,
    updateRule: null,
    deleteRule: null,
    fields: [
      { name: "user", type: "relation", required: false, collectionId: users.id, cascadeDelete: false, maxSelect: 1 },
      { name: "document_version", type: "text", required: true, max: 20 },
      { name: "scopes", type: "json", required: true, maxSize: 2000 },
      { name: "granted_at", type: "text", required: true, max: 30 },
      { name: "withdrawn_at", type: "text", max: 30 },
      { name: "created", type: "autodate", onCreate: true, onUpdate: false },
    ],
  });
  app.save(consents);
}, (app) => {
  for (const name of ["consents", "sync_tokens", "day_log", "votes", "daily", "workouts"]) {
    try { app.delete(app.findCollectionByNameOrId(name)); } catch (_) {}
  }
  const users = app.findCollectionByNameOrId("users");
  for (const f of ["birth_year", "sex", "menopause_status", "timezone", "habits", "kit", "routine"]) {
    users.fields.removeByName(f);
  }
  users.updateRule = "id = @request.auth.id";
  app.save(users);
});
