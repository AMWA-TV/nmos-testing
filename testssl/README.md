# testssl.sh

In order to test BCP-003-01, the `testssl.sh` script must be placed in this directory with 'execute' permission enabled. This tool is known to work on Linux and Mac OS, but requires [Ubuntu terminal](https://tutorials.ubuntu.com/tutorial/tutorial-ubuntu-on-windows) for usage on Windows. Note that the Linux terminal approach on Windows will be significantly slower to run than a pure Linux system (or Linux VM on Windows).

The minimum and tested versions are listed in `EXTERNAL_TOOLS` in [nmostesting/ExternalTools.py](../nmostesting/ExternalTools.py).
Please download the tested version from <https://github.com/testssl/testssl.sh/tags>, then untar the results into this directory.

Alternatively, use the following commands which can be executed from within this `testssl` directory.

```shell
TESTSSL_VERSION=3.0.7
wget https://github.com/testssl/testssl.sh/archive/v${TESTSSL_VERSION}.tar.gz
tar -xvzf v${TESTSSL_VERSION}.tar.gz --strip-components=1
```
