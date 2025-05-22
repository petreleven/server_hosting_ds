console.log("1. Start");

function asyncTask() {
  setTimeout(() => {
    console.log("2. Doing async task (after 2 seconds)");
  }, 2000);
}

asyncTask();
console.log("3. End");





console.log("1. Start");

function delay(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

async function runAsync() {
  console.log("2. Waiting...");
  await delay(2000);
  console.log("3. Async done");
}

runAsync();
console.log("4. End");




console.log("1. Start");

fetch('https://jsonplaceholder.typicode.com/posts/1')
  .then(response => response.json())
  .then(data => {
    console.log("2. Fetched with fetch:", data.title);
  });

console.log("3. End");
console.log("1. Start");

let xhr = new XMLHttpRequest();
xhr.open('GET', 'https://jsonplaceholder.typicode.com/posts/1', true); // true = async

xhr.onload = function () {
  if (xhr.status === 200) {
    let data = JSON.parse(xhr.responseText);
    console.log("2. Fetched with XHR (async):", data.title);
  }
};

xhr.send();

console.log("3. End");
