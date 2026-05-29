# vendor/

Small redistributable dependency kept in-tree for the parity test suite.

## marathon-utils (NOT vendored)

The cross-validation test (`tests/test_perl_parity.py`) compares our parser
against [Hopper262/marathon-utils](https://github.com/Hopper262/marathon-utils).
That upstream is **not** bundled here — it has no license, so we don't
redistribute it. The test skips unless you provide a local clone:

```bash
git clone --depth=1 https://github.com/Hopper262/marathon-utils
export MARATHON_UTILS_DIR=$PWD/marathon-utils   # or place it beside this repo
pytest tests/test_perl_parity.py
```

## `perl-lib/`

Pure-Perl `XML::Writer` module needed by the marathon-utils scripts during the
parity test. Freely redistributable under the same terms as Perl itself
(Artistic / GPL). Source:
[CPAN XML-Writer-0.900](https://metacpan.org/release/JOSEPHW/XML-Writer-0.900).
