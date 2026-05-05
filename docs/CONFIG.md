# CONFIG

SilverBullet v2 configuration for the Hermes hub space.

`silverbulletmd/silverbullet-atlas` no longer exists as a separate repo and was
not folded into core. The closest in-vault graph experience for v2 is
[silverbullet-graphview](https://github.com/deepkn/silverbullet-graphview),
which is enabled below alongside the Mermaid plug used by [[OrgGraph]].

After editing this page, run the `Plugs: Update` command from the SB command
palette.

```space-lua
config.set {
  plugs = {
    "ghr:deepkn/silverbullet-graphview",
    "github:silverbulletmd/silverbullet-mermaid/mermaid.plug.js",
  },
}
```
