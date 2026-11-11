/// <reference path="../pb_data/types.d.ts" />

// Sealed vaults (backend/app/vault.py). Everything personal moves out of plain fields and
// rows into one sealed box per person, which only that person's key can open.
//   vaults: the box, its public key (for sealing), and the person's key locked by their
//           password and by their recovery key. We can't open any of them.
//   inbox:  things sealed while the person was away (watch Shortcut, Health export),
//           folded into the vault the next time they use Charge.
// Nobody but the API (superuser) can list, read or write either.
migrate((app) => {
  const users = app.findCollectionByNameOrId("users");
  const sealed = (name, fields) => {
    app.save(new Collection({
      name,
      type: "base",
      listRule: null,
      viewRule: null,
      createRule: null,
      updateRule: null,
      deleteRule: null,
      fields: [
        { name: "user", type: "relation", required: true, collectionId: users.id, cascadeDelete: true, maxSelect: 1 },
        ...fields,
        { name: "created", type: "autodate", onCreate: true, onUpdate: false },
        { name: "updated", type: "autodate", onCreate: true, onUpdate: true },
      ],
      indexes: name === "vaults" ? ["CREATE UNIQUE INDEX idx_vaults_user ON vaults (user)"]
                                 : ["CREATE INDEX idx_inbox_user ON inbox (user)"],
    }));
  };
  sealed("vaults", [
    { name: "pk", type: "text", required: true, min: 64, max: 64, pattern: "^[0-9a-f]{64}$" },
    { name: "box", type: "text", required: true, max: 8000000 },
    { name: "kdf", type: "json", maxSize: 2000 },
    { name: "wrap_pw", type: "text", max: 200 },
    { name: "wrap_rk", type: "text", max: 200 },
  ]);
  sealed("inbox", [{ name: "box", type: "text", required: true, max: 8000000 }]);

  // Profile fields now live in the vault; people can't write the old plain ones either.
  users.updateRule = "id = @request.auth.id && @request.body.birth_year:isset = false && @request.body.kit:isset = false && @request.body.habits:isset = false && @request.body.routine:isset = false && @request.body.sex:isset = false && @request.body.menopause_status:isset = false && @request.body.timezone:isset = false";
  app.save(users);
}, (app) => {
  for (const name of ["inbox", "vaults"]) {
    try { app.delete(app.findCollectionByNameOrId(name)); } catch (_) {}
  }
});
