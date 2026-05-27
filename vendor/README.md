# vendor/

Third-party reference implementations kept in-tree for the parity test suite.

## `marathon-utils/`

Perl scripts by [Hopper262](https://github.com/Hopper262/marathon-utils).
Vendored at the commit that was current when py-marathon-utils v0.1.0 shipped.
We don't redistribute or modify these; they exist so `tests/test_perl_parity.py`
can run `map2xml.pl` and diff its output against ours. See the upstream repo
for license/attribution questions.

To refresh:

```bash
rm -rf vendor/marathon-utils
git clone --depth=1 https://github.com/Hopper262/marathon-utils vendor/marathon-utils
rm -rf vendor/marathon-utils/.git
```

## `perl-lib/`

Pure-Perl `XML::Writer` module needed by the marathon-utils scripts. We vendor
it so the parity test runs without CPAN setup. Source:
[CPAN XML-Writer-0.900](https://metacpan.org/release/JOSEPHW/XML-Writer-0.900).
