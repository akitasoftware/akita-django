# Akita Django Integration

This package contains a Django `TestClient` extension that instruments Django
integration tests to capture requests and responses to the service under test.
You can drop in the `AkitaTestClient` everywhere you use Django's `TestClient`,
and Akita will use your integration tests to build a spec for your service.

Why build specs?  A spec shows your service's APIs.  Using Akita to build specs
from your integration tests makes it clear what APIs your code implements --
and you can diff specs, showing what impact a code change will have on your
customers.  For more info, see [Catching Breaking Changes
Faster](https://docs.akita.software/docs) in the Akita docs.
