# RAD Assumption Tagging Standards

Quick reference for assumption tagging during development.

## Tagging Syntax

When writing code, ALWAYS tag assumptions that could cause production failures:

```javascript
// #CRITICAL: [category]: [assumption that could cause outages/data loss]
// #VERIFY: [defensive code required]
// Example: Payment processing, auth flows, concurrent writes

// #ASSUME: [category]: [assumption that could cause bugs]
// #VERIFY: [validation needed]
// Example: UI state, form validation, API responses

// #EDGE: [category]: [assumption about uncommon scenarios]
// #VERIFY: [optional improvement]
// Example: Browser compatibility, slow networks
```

## Critical Assumption Categories (MANDATORY Tagging)

### Timing Dependencies

```javascript
// #CRITICAL: timing: React state update assumed complete before navigation
// #VERIFY: Use callback or state confirmation
setUserData(newData);
navigateToProfile(userData.id);  // ❌ Race condition
```

### External Resources

```javascript
// #CRITICAL: api: Payment gateway assumed to respond within 5s
// #VERIFY: Add timeout and retry logic
const result = await paymentGateway.charge(amount);  // ❌ No timeout
```

### Data Integrity

```javascript
// #CRITICAL: validation: User input assumed sanitized
// #VERIFY: Add input validation and sanitization
function executeQuery(userInput) {
    return db.query(userInput);  // ❌ SQL injection risk
}
```

### Concurrency

```javascript
// #CRITICAL: concurrency: Database transaction isolation assumed
// #VERIFY: Add explicit locks and conflict resolution
async function updateBalance(userId, amount) {
    const user = await db.users.findById(userId);
    user.balance += amount;  // ❌ Race condition
    return user.save();
}
```

### Security

```javascript
// #CRITICAL: auth: User session assumed valid
// #VERIFY: Add token validation and refresh logic
function getCurrentUser() {
    return localStorage.getItem('currentUser');  // ❌ No validation
}
```

### Payment/Financial

```javascript
// #CRITICAL: payment: Transaction assumed atomic
// #VERIFY: Add rollback and idempotency checks
await chargeCard(amount);
await updateInventory(itemId);  // ❌ No transaction boundary
```

## Standard Assumption Categories (Use #ASSUME)

### State Management

```javascript
// #ASSUME: state: Component state persists across re-renders
// #VERIFY: Add useEffect cleanup or state persistence
const [data, setData] = useState(initialData);
```

### API Responses

```javascript
// #ASSUME: api: API always returns 200 or 404
// #VERIFY: Add error handling for 500, timeout, network errors
const response = await fetch(url);
```

### Form Validation

```javascript
// #ASSUME: validation: Email format validated on submit
// #VERIFY: Add real-time validation or backend verification
<input type="email" />
```

## Edge Case Categories (Use #EDGE)

### Browser Compatibility

```javascript
// #EDGE: browser: Clipboard API available in all browsers
// #VERIFY: Add fallback using document.execCommand
navigator.clipboard.writeText(text);
```

### Network Conditions

```javascript
// #EDGE: network: Assuming high-speed connection
// #VERIFY: Add loading states, timeout, or offline fallback
const data = await fetchLargeDataset();
```

### Performance

```javascript
// #EDGE: performance: Assuming dataset <1000 items
// #VERIFY: Add pagination or virtualization for large lists
{items.map(item => <ListItem key={item.id} />)}
```

## Verification Status Markers

After verification, mark assumptions as verified:

```javascript
// #CRITICAL: [VERIFIED-2025-01-30] payment: Timeout added
// #VERIFY: ✅ Added timeout and retry with exponential backoff
async function processPayment(amount) {
    return Promise.race([
        paymentGateway.charge(amount),
        timeout(5000)
    ]);
}
```

## Anti-Patterns (Do NOT Tag)

```javascript
// ❌ BAD: Over-tagging trivial assumptions
// #ASSUME: math: Addition returns sum
const total = price + tax;

// ✅ GOOD: Only tag production-impacting assumptions
// #CRITICAL: payment: Tax calculation assumed to use correct jurisdiction
const total = price + calculateTax(price, userLocation);
```

## Workflow Integration

```bash
# Before commit — verify changed files
/rad/verify --scope=changed-files

# Critical only
/rad/verify --strategy=critical-only

# Full project inventory
/rad/list
```
