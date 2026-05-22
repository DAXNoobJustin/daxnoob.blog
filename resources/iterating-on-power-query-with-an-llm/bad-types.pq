// bad-types.pq — intentional type error: text + number.
// PQTest returns Status=Failed with the operator, both types, and the actual values.
let
    a = "hello",
    b = a + 5
in
    b
