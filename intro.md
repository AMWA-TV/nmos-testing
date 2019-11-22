### What does it do?

- This tool creates a simple web service which tests implementations of the NMOS APIs, currently:

    - IS-04 Node API
    - IS-04 Registry APIs
    - IS-04 Node API (Peer to Peer)
    - IS-05 Connection Management API
    - IS-05 Interaction with IS-04
    - IS-06 Network Control API
    - IS-07 Event & Tally API
    - IS-08 Channel Mapping API
    - IS-08 Interaction with IS-04
    - IS-09 System API
    - IS-10 Authorization API
    - BCP-002-01 Natural Grouping (see IS-04 Node API)
    - BCP-003-01 Secure API Communications
    - BCP-003-02 Authorization (see IS-10 Authorization API)

### Why does it matter?

- Provides an aid to developers
- Check conformance to specs before industry plug-fests
    - Compulsory for JT-NM TR-1001 Testing
- Too time consuming to test everything manually
- Helps identify where interoperability issues lie with multiple vendors

### How does it work?

- Downloads each NMOS specification using Git
- Parses the RAML API definition and JSON schemas in order to construct basic tests automatically
- Merges automatically constructed tests with manually defined ones
- Launches a web interface to run tests from

For more details see the [GitHub repo]({{ site.github.repository_url}})
