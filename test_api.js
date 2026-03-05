const token = process.env.INDSTOCKS_TOKEN || "MISSING";
console.log("Token length:", token.length);

async function testApi() {
    try {
        const res = await fetch(`https://api.indstocks.com/v1/market/instruments?search=SBIN&exchange=NFO`, {
            headers: { "Authorization": `Bearer ${token}` }
        });
        console.log("Status:", res.status);
        const json = await res.json();
        console.log("Items:", json.data.length);
        json.data.slice(0, 10).forEach(d => {
            console.log(`- ${d.name} | ${d.scripCode} | expiry: ${d.expiry}`);
        });
    } catch (e) { console.error(e); }
}
testApi();
