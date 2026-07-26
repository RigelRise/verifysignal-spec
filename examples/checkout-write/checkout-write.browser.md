# Skill: checkout-write

Completes checkout for a signed-in shopper. `submit-order` is the **commit
step** — the runtime watches it against the declared side-effect policy and
captures the created order URL as a runtime output.

Credentials are read from the environment (`SHOP_USER` / `SHOP_PASSWORD`) at run
time and never written to disk.

```yaml
schemaVersion: qa-skill/v1
id: skill.checkout-write
browser:
  targets:
    placeOrderButton:
      testId: place-order
      domainSemantics: Place order button
    confirmationHeading:
      testId: order-confirmed
      domainSemantics: Order confirmation heading
    orderNumber:
      testId: order-number
      domainSemantics: Created order reference
  steps:
    - id: open-review
      action: navigate
      value: "{{parameters.baseUrl}}/checkout/review"
    - id: submit-order
      action: click
      target: placeOrderButton
    - id: await-order-created
      action: awaitNetwork
      match:
        method: POST
        urlContains: /api/orders
        expectedStatus: 201
    - id: capture-confirmation
      action: captureScreenshot
  assertions:
    - id: order-confirmed
      kind: text
      target: confirmationHeading
      expected: "Order confirmed"
      gateId: order-confirmed
    - id: order-reference-visible
      kind: visible
      target: orderNumber
      gateId: order-reference
```
